"""TTS adapters: Gemini multi-speaker TTS (recommended quality/price) and
ElevenLabs (v3 text-to-dialogue, premium).

Both consume a script of `NAME: line` dialogue turns and write one audio file per
chunk into an output directory. Chunks are stitched later with ffmpeg.
"""

from __future__ import annotations

import os
import re
import struct
import sys
import time
from pathlib import Path

TURN_RE = re.compile(r"^([A-Z][A-Za-z0-9_ ]{0,30}):\s*(.+)$")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_turns(script: str) -> list[tuple[str, str]]:
    """Parse `NAME: text` lines into (speaker, text) turns; tolerate stray lines by
    appending them to the previous turn."""
    turns: list[tuple[str, str]] = []
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = TURN_RE.match(line)
        if m:
            turns.append((m.group(1).strip(), m.group(2).strip()))
        elif turns:
            turns.append((turns[-1][0], line))
    return turns


def chunk_turns(turns: list[tuple[str, str]], max_chars: int) -> list[list[tuple[str, str]]]:
    """Group consecutive turns into chunks below max_chars (never splitting a turn)."""
    chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    size = 0
    for turn in turns:
        turn_len = len(turn[0]) + len(turn[1]) + 4
        if current and size + turn_len > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(turn)
        size += turn_len
    if current:
        chunks.append(current)
    return chunks


def _write_wav(path: Path, pcm: bytes, rate: int = 24000) -> None:
    """Wrap raw 16-bit mono PCM in a WAV header."""
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1,
        rate, rate * 2, 2, 16, b"data", len(pcm),
    )
    path.write_bytes(header + pcm)


class GeminiTTS:
    """Google Gemini native multi-speaker TTS. ~$1.80/audio-hour on Flash-tier TTS
    models — the quality/price winner for two-host dialogue."""

    suffix = ".wav"

    def __init__(self, cfg: dict, hosts: dict[str, str]):
        from google import genai

        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model = cfg.get("model", "gemini-3.1-flash-tts")
        self.max_chars = int(cfg.get("max_chars_per_request", 4500))
        # map host name -> prebuilt voice
        voices = cfg.get("voices", {})
        self.voices = {
            hosts["host_a"]: voices.get("host_a", "Puck"),
            hosts["host_b"]: voices.get("host_b", "Charon"),
        }
        self.style = cfg.get(
            "style",
            "Read this two-host podcast conversation naturally and energetically, "
            "like close friends recording a show. React genuinely to each other.",
        )

    def synthesize_chunk(self, turns: list[tuple[str, str]], out_path: Path) -> None:
        from google.genai import types

        transcript = "\n".join(f"{s}: {t}" for s, t in turns)
        speaker_configs = [
            types.SpeakerVoiceConfig(
                speaker=name,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                ),
            )
            for name, voice in self.voices.items()
        ]
        response = self.client.models.generate_content(
            model=self.model,
            contents=f"{self.style}\n\n{transcript}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                        speaker_voice_configs=speaker_configs
                    )
                ),
            ),
        )
        pcm = response.candidates[0].content.parts[0].inline_data.data
        _write_wav(out_path, pcm)


class ElevenLabsTTS:
    """ElevenLabs v3 text-to-dialogue (premium expressiveness) via raw HTTP."""

    suffix = ".mp3"

    def __init__(self, cfg: dict, hosts: dict[str, str]):
        import requests  # noqa: F401  (validated here so failures surface early)

        self.api_key = os.environ["ELEVENLABS_API_KEY"]
        self.model = cfg.get("model", "eleven_v3")
        self.max_chars = int(cfg.get("max_chars_per_request", 4000))
        voices = cfg.get("voices", {})
        self.voice_ids = {
            hosts["host_a"]: voices.get("host_a", "JBFqnCBsd6RMkjVDRZzb"),  # George
            hosts["host_b"]: voices.get("host_b", "Xb7hH8MSUJpSbSDYk0k2"),  # Alice
        }

    def synthesize_chunk(self, turns: list[tuple[str, str]], out_path: Path) -> None:
        import requests

        inputs = [
            {"text": text, "voice_id": self.voice_ids.get(speaker, next(iter(self.voice_ids.values())))}
            for speaker, text in turns
        ]
        resp = requests.post(
            "https://api.elevenlabs.io/v1/text-to-dialogue",
            headers={"xi-api-key": self.api_key},
            json={"inputs": inputs, "model_id": self.model},
            params={"output_format": "mp3_44100_128"},
            timeout=600,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)


def make_tts(cfg: dict, hosts: dict[str, str]):
    provider = cfg.get("provider", "gemini")
    if provider == "gemini":
        return GeminiTTS(cfg, hosts)
    if provider == "elevenlabs":
        return ElevenLabsTTS(cfg, hosts)
    raise ValueError(f"Unknown TTS provider: {provider}")


def synthesize_script(tts, script: str, out_dir: Path) -> list[Path]:
    """Chunk the full script and synthesize each chunk, with resume support
    (existing non-empty files are skipped) and simple retry."""
    out_dir.mkdir(parents=True, exist_ok=True)
    turns = parse_turns(script)
    chunks = chunk_turns(turns, tts.max_chars)
    paths: list[Path] = []
    for i, chunk in enumerate(chunks, 1):
        path = out_dir / f"chunk_{i:04d}{tts.suffix}"
        paths.append(path)
        if path.exists() and path.stat().st_size > 0:
            continue
        for attempt in range(3):
            try:
                log(f"  TTS chunk {i}/{len(chunks)} ({sum(len(t[1]) for t in chunk)} chars)")
                tts.synthesize_chunk(chunk, path)
                break
            except Exception as e:  # noqa: BLE001 — retry then re-raise
                if attempt == 2:
                    raise
                log(f"  chunk {i} failed ({e}); retrying in {5 * (attempt + 1)}s")
                time.sleep(5 * (attempt + 1))
    return paths
