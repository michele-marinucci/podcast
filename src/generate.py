"""Acquired-style podcast generator.

Pipeline:  research -> outline -> segment scripts -> polish -> TTS -> stitch

Every stage checkpoints to disk under output/<slug>/, so re-running resumes
where it left off. Delete a stage's artifact to regenerate it.

Usage:
    python -m src.generate "Costco"
    python -m src.generate NVDA --runtime 210
    python -m src.generate "Costco" --script-only
    python -m src.generate "Costco" --tts-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from .llm import make_llm, log
from .tts import make_tts, synthesize_script

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"


def render(template: str, **vars: object) -> str:
    for key, value in vars.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def load_prompt(name: str, **vars: object) -> str:
    return render((PROMPTS / name).read_text(), **vars)


def parse_json_lenient(text: str) -> dict:
    """Parse JSON that may be wrapped in markdown fences or prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in outline response")
    return json.loads(text[start : end + 1])


def word_count(script: str) -> int:
    return len(script.split())


# ---------------------------------------------------------------- stages


def stage_research(cfg: dict, company: str, out: Path) -> str:
    path = out / "01_dossier.md"
    if path.exists():
        log(f"[research] using cached {path}")
        return path.read_text()

    # Local source documents (10-Ks, articles...) dropped in sources/ are appended.
    extra = ""
    sources_dir = out / "sources"
    if sources_dir.is_dir():
        docs = sorted(p for p in sources_dir.iterdir() if p.suffix in (".md", ".txt"))
        if docs:
            extra = "\n\n# PROVIDED SOURCE DOCUMENTS\n\n" + "\n\n---\n\n".join(
                f"## {p.name}\n\n{p.read_text()}" for p in docs
            )

    prompt = load_prompt(
        "01_research.md", COMPANY=company, DATE=dt.date.today().isoformat()
    ) + extra

    research_cfg = cfg.get("research", {})
    provider = research_cfg.get("provider", "anthropic")
    log(f"[research] provider={provider} (this is the slow stage)")
    if provider == "anthropic":
        from .llm import AnthropicLLM

        llm = AnthropicLLM(model=research_cfg.get("model", "claude-opus-4-8"))
        dossier = llm.research(prompt, max_searches=int(research_cfg.get("max_searches", 30)))
    else:
        # No live web search: model knowledge + provided sources only.
        llm = make_llm(cfg["script"])
        dossier = llm.generate(
            system="You are a meticulous business researcher.", user=prompt, max_tokens=48000
        )

    path.write_text(dossier)
    log(f"[research] wrote {path} ({word_count(dossier)} words)")
    return dossier


def stage_outline(cfg: dict, company: str, dossier: str, out: Path) -> dict:
    path = out / "02_outline.json"
    if path.exists():
        log(f"[outline] using cached {path}")
        return json.loads(path.read_text())

    ep = cfg["episode"]
    runtime = int(ep["runtime_minutes"])
    target_words = int(runtime * int(ep.get("words_per_minute", 155)))
    segment_count = int(ep.get("segment_count", max(8, round(target_words / 2600))))
    words_per_segment = round(target_words / segment_count / 50) * 50

    system = load_prompt(
        "02_outline.md",
        COMPANY=company,
        RUNTIME_MINUTES=runtime,
        TARGET_WORDS=target_words,
        SEGMENT_COUNT=segment_count,
        WORDS_PER_SEGMENT=words_per_segment,
    )
    llm = make_llm(cfg["script"])
    log(f"[outline] {segment_count} segments x ~{words_per_segment} words")
    raw = llm.generate(system=system, user=f"RESEARCH DOSSIER:\n\n{dossier}", max_tokens=24000)
    outline = parse_json_lenient(raw)
    path.write_text(json.dumps(outline, indent=2))
    log(f"[outline] wrote {path} — \"{outline.get('episode_title', '?')}\"")
    return outline


def stage_segments(cfg: dict, company: str, dossier: str, outline: dict, out: Path) -> list[str]:
    seg_dir = out / "segments"
    seg_dir.mkdir(exist_ok=True)
    llm = make_llm(cfg["script"])
    hosts = cfg["hosts"]
    ep = cfg["episode"]

    outline_context = json.dumps(
        {k: outline[k] for k in ("episode_title", "logline", "big_questions", "running_threads") if k in outline},
        indent=2,
    )
    segments: list[str] = []
    covered: list[str] = []

    for seg in outline["segments"]:
        seg_id = int(seg["id"])
        path = seg_dir / f"segment_{seg_id:02d}.txt"
        if path.exists():
            text = path.read_text()
            log(f"[segments] {seg_id}: cached ({word_count(text)} words)")
        else:
            system = load_prompt(
                "03_segment_writer.md",
                COMPANY=company,
                RUNTIME_MINUTES=ep["runtime_minutes"],
                HOST_A=hosts["host_a"],
                HOST_B=hosts["host_b"],
                TARGET_WORDS=seg.get("target_words", 2600),
            )
            prev_tail = " (This is the first segment — open the show cold.)"
            if segments:
                prev_tail = "\n".join(segments[-1].strip().splitlines()[-8:])
            user = (
                f"RESEARCH DOSSIER:\n\n{dossier}\n\n"
                f"EPISODE CONTEXT:\n\n{outline_context}\n\n"
                f"ALREADY COVERED IN PRIOR SEGMENTS (do not repeat):\n"
                + ("\n".join(f"- {c}" for c in covered) or "- (nothing yet)")
                + f"\n\nCLOSING LINES OF THE PREVIOUS SEGMENT:\n{prev_tail}\n\n"
                f"YOUR SEGMENT BRIEF:\n\n{json.dumps(seg, indent=2)}\n\n"
                f"Write segment {seg_id} now."
            )
            log(f"[segments] {seg_id}/{len(outline['segments'])}: writing \"{seg.get('title', '')}\"")
            text = llm.generate(system=system, user=user, max_tokens=16000)
            path.write_text(text)
            log(f"[segments] {seg_id}: {word_count(text)} words")
        segments.append(text)
        covered.append(f"Segment {seg_id} — {seg.get('title', '')}: {seg.get('narrative_goal', '')}")
    return segments


AUDIO_TAGS_RULE = (
    "5. **Expressive audio tags (ElevenLabs v3).** Sparingly add inline tags where they\n"
    "   genuinely help delivery — [laughs], [sighs], [whispers], [excited], [curious] —\n"
    "   at most one tag every four to six turns, placed immediately before the words\n"
    "   they color."
)


def stage_polish(cfg: dict, segments: list[str], out: Path) -> str:
    script_path = out / "03_script.txt"
    if script_path.exists():
        log(f"[polish] using cached {script_path}")
        return script_path.read_text()

    tags_rule = AUDIO_TAGS_RULE if cfg["tts"].get("provider") == "elevenlabs" else ""
    system = load_prompt("04_polish.md", AUDIO_TAGS_RULE=tags_rule)
    llm = make_llm(cfg["script"])
    pol_dir = out / "segments_polished"
    pol_dir.mkdir(exist_ok=True)

    polished: list[str] = []
    for i, seg in enumerate(segments):
        path = pol_dir / f"segment_{i + 1:02d}.txt"
        if path.exists():
            polished.append(path.read_text())
            continue
        prev_tail = "\n".join(segments[i - 1].strip().splitlines()[-6:]) if i > 0 else "(episode start)"
        next_head = "\n".join(segments[i + 1].strip().splitlines()[:6]) if i + 1 < len(segments) else "(episode end)"
        user = (
            f"PREVIOUS SEGMENT ENDS WITH:\n{prev_tail}\n\n"
            f"NEXT SEGMENT BEGINS WITH:\n{next_head}\n\n"
            f"SEGMENT TO POLISH:\n\n{seg}"
        )
        log(f"[polish] segment {i + 1}/{len(segments)}")
        text = llm.generate(system=system, user=user, max_tokens=16000)
        path.write_text(text)
        polished.append(text)

    script = "\n\n".join(p.strip() for p in polished)
    script_path.write_text(script)
    log(f"[polish] final script: {word_count(script)} words "
        f"(~{word_count(script) // int(cfg['episode'].get('words_per_minute', 155))} min)")
    return script


def stage_audio(cfg: dict, script: str, out: Path) -> Path:
    hosts = cfg["hosts"]
    tts = make_tts(cfg["tts"], hosts)
    chunk_paths = synthesize_script(tts, script, out / "audio")

    episode = out / "episode.mp3"
    concat_list = out / "audio" / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in chunk_paths))
    log(f"[stitch] concatenating {len(chunk_paths)} chunks -> {episode}")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:a", "libmp3lame", "-b:a", "128k", str(episode)],
        check=True, capture_output=True,
    )
    return episode


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an Acquired-style deep-dive podcast")
    parser.add_argument("company", help="Company name or stock ticker, e.g. 'Costco' or NVDA")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--runtime", type=int, help="Override runtime in minutes")
    parser.add_argument("--script-only", action="store_true", help="Stop before TTS")
    parser.add_argument("--tts-only", action="store_true", help="Only run TTS on an existing script")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    if args.runtime:
        cfg["episode"]["runtime_minutes"] = args.runtime

    slug = re.sub(r"[^a-z0-9]+", "-", args.company.lower()).strip("-")
    out = ROOT / "output" / slug
    out.mkdir(parents=True, exist_ok=True)
    log(f"== {args.company} -> {out}")

    if args.tts_only:
        script = (out / "03_script.txt").read_text()
    else:
        dossier = stage_research(cfg, args.company, out)
        outline = stage_outline(cfg, args.company, dossier, out)
        segments = stage_segments(cfg, args.company, dossier, outline, out)
        script = stage_polish(cfg, segments, out)

    if args.script_only:
        log("[done] script-only run complete")
        return

    episode = stage_audio(cfg, script, out)
    log(f"[done] {episode}")


if __name__ == "__main__":
    main()
