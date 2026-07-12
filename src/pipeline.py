"""Episode pipeline for the web app.

Phase A (run_until_checkpoint):  source map -> fetch corpus -> dossier -> outline
                                 -> status "awaiting_approval"
Phase B (resume_after_approval): per segment: write -> fact audit -> polish -> TTS
                                 (chapters stream to the UI as they finish) -> stitch

All state lives in output/<job_id>/state.json so the web layer just reads it.
Set DRY_RUN=1 to exercise the whole flow with canned artifacts and silent audio
(no API keys needed).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from .fetchers import build_corpus
from .generate import load_prompt, parse_json_lenient, word_count, AUDIO_TAGS_RULE
from .llm import make_llm
from .tts import make_tts, synthesize_script

ROOT = Path(__file__).resolve().parent.parent
DRY = os.environ.get("DRY_RUN") == "1"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Job:
    def __init__(self, job_dir: Path):
        self.dir = job_dir
        self.state_path = job_dir / "state.json"
        self.state = {}
        if self.state_path.exists():
            for attempt in range(3):  # tolerate a concurrent writer
                try:
                    self.state = json.loads(self.state_path.read_text())
                    break
                except json.JSONDecodeError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)

    def update(self, **kwargs) -> None:
        self.state.update(kwargs)
        self.state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        tmp = self.state_path.with_suffix(".tmp")  # atomic swap — readers never see a partial file
        tmp.write_text(json.dumps(self.state, indent=2))
        tmp.replace(self.state_path)

    def set_chapter(self, seg_id: int, **kwargs) -> None:
        for ch in self.state.get("chapters", []):
            if ch["id"] == seg_id:
                ch.update(kwargs)
        self.update(chapters=self.state["chapters"])


def create_job(company: str, runtime: int, preferences: str, uploads: list[str]) -> Job:
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    job_id = f"{slug}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    job_dir = ROOT / "output" / job_id
    (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
    job = Job(job_dir)
    job.update(
        id=job_id, company=company, status="queued", message="Queued",
        runtime_minutes=runtime, preferences=preferences, uploads=uploads,
        episode_title=None, logline=None, chapters=[], sources=[], error=None,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    return job


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


# ---------------------------------------------------------------- phase A


def _research_llm(cfg: dict):
    from .llm import AnthropicLLM

    research_cfg = cfg.get("research", {})
    return AnthropicLLM(model=research_cfg.get("model", "claude-opus-4-8"))


def run_until_checkpoint(job: Job) -> None:
    try:
        cfg = load_config()
        company = job.state["company"]
        today = dt.date.today().isoformat()

        # -- stage 0: source map
        job.update(status="researching", message="Mapping the best sources — books, interviews, filings")
        sm_path = job.dir / "00_source_map.json"
        if sm_path.exists():
            source_map = json.loads(sm_path.read_text())
        elif DRY:
            source_map = {"books": [], "interviews": [], "filings": [], "articles": [], "archives": []}
            sm_path.write_text(json.dumps(source_map))
        else:
            uploads_desc = "\n".join(f"- {u}" for u in job.state["uploads"]) or "none"
            prompt = load_prompt("00_source_map.md", COMPANY=company, DATE=today,
                                 USER_MATERIALS=uploads_desc)
            raw = _research_llm(cfg).research(prompt, max_tokens=16000, max_searches=15)
            source_map = parse_json_lenient(raw)
            sm_path.write_text(json.dumps(source_map, indent=2))

        # -- stage 0b: fetch corpus
        job.update(status="fetching", message="Pulling filings, transcripts, and interviews")
        corpus_path = job.dir / "corpus.txt"
        if corpus_path.exists():
            corpus = corpus_path.read_text()
            manifest = json.loads((job.dir / "corpus_manifest.json").read_text())
        else:
            corpus, manifest = build_corpus(company, source_map, job.dir / "uploads", job.dir)
        job.update(sources=manifest)

        # -- stage 1: dossier
        job.update(status="researching", message="Writing the research dossier")
        dossier_path = job.dir / "01_dossier.md"
        if dossier_path.exists():
            dossier = dossier_path.read_text()
        elif DRY:
            dossier = (f"## 1. Company Snapshot\n{company} is a test company. Revenue: "
                       "one hundred billion dollars (FY2025) [S1].\n\n## 16. Source Register\n"
                       "[S1] | user_upload | test | -")
            dossier_path.write_text(dossier)
        else:
            prompt = load_prompt("01_research.md", COMPANY=company, DATE=today)
            user = f"{prompt}\n\n# CORPUS\n\n{corpus}" if corpus else prompt
            dossier = _research_llm(cfg).research(user, max_tokens=64000, max_searches=20)
            dossier_path.write_text(dossier)

        # -- stage 2: outline
        job.update(status="drafting_outline", message="Structuring the episode")
        outline = _make_outline(cfg, job, company, dossier)
        chapters = [
            {"id": s["id"], "title": s.get("title", f"Chapter {s['id']}"),
             "teaser": s.get("teaser", ""), "status": "pending", "audio": None}
            for s in outline["segments"]
        ]
        job.update(
            status="awaiting_approval",
            message="Outline ready — review and approve to generate the episode",
            episode_title=outline.get("episode_title"),
            logline=outline.get("logline"),
            chapters=chapters,
        )
    except Exception as e:  # noqa: BLE001
        log(f"[job {job.state.get('id')}] phase A failed: {e}")
        job.update(status="error", error=str(e), message="Generation failed")
        raise


def _make_outline(cfg: dict, job: Job, company: str, dossier: str) -> dict:
    path = job.dir / "02_outline.json"
    if path.exists():
        return json.loads(path.read_text())
    ep = cfg["episode"]
    runtime = int(job.state.get("runtime_minutes") or ep["runtime_minutes"])
    wpm = int(ep.get("words_per_minute", 155))
    target_words = runtime * wpm
    segment_count = int(ep.get("segment_count", max(3, round(target_words / 2600))))
    words_per_segment = max(100, round(target_words / segment_count / 50) * 50)

    if DRY:
        outline = {
            "episode_title": f"{company}: The Complete Story",
            "logline": "A dry-run test episode.",
            "big_questions": ["?"], "running_threads": [],
            "segments": [
                {"id": i, "arc_part": "test", "title": f"Chapter {i}",
                 "teaser": f"Teaser {i}", "target_words": 60,
                 "narrative_goal": "test", "emotional_register": "neutral",
                 "beats": ["beat"], "must_use_facts": [], "handoff": "next"}
                for i in (1, 2, 3)
            ],
        }
    else:
        system = load_prompt(
            "02_outline.md", COMPANY=company, RUNTIME_MINUTES=runtime,
            TARGET_WORDS=target_words, SEGMENT_COUNT=segment_count,
            WORDS_PER_SEGMENT=words_per_segment,
            USER_PREFERENCES=job.state.get("preferences") or "No special preferences.",
        )
        llm = make_llm(cfg["script"])
        raw = llm.generate(system=system, user=f"RESEARCH DOSSIER:\n\n{dossier}", max_tokens=24000)
        outline = parse_json_lenient(raw)
    path.write_text(json.dumps(outline, indent=2))
    return outline


# ---------------------------------------------------------------- phase B


def resume_after_approval(job: Job, notes: dict[str, str], global_note: str) -> None:
    try:
        cfg = load_config()
        company = job.state["company"]
        dossier = (job.dir / "01_dossier.md").read_text()
        outline = json.loads((job.dir / "02_outline.json").read_text())

        for seg in outline["segments"]:
            note = notes.get(str(seg["id"]))
            if note:
                seg["user_notes"] = note
        if global_note:
            outline["user_global_note"] = global_note
        (job.dir / "02_outline.json").write_text(json.dumps(outline, indent=2))

        hosts = cfg["hosts"]
        llm = None if DRY else make_llm(cfg["script"])
        tts = None if DRY else make_tts(cfg["tts"], hosts)
        seg_dir = job.dir / "segments"
        audio_dir = job.dir / "audio"
        seg_dir.mkdir(exist_ok=True)
        audio_dir.mkdir(exist_ok=True)

        outline_context = json.dumps(
            {k: outline[k] for k in
             ("episode_title", "logline", "big_questions", "running_threads", "user_global_note")
             if k in outline},
            indent=2,
        )
        segments: list[str] = []
        covered: list[str] = []
        segment_audio: list[Path] = []

        for seg in outline["segments"]:
            seg_id = int(seg["id"])
            job.update(status="writing", message=f"Writing chapter {seg_id}: {seg.get('title', '')}")
            job.set_chapter(seg_id, status="writing")

            text = _write_segment(cfg, llm, job, company, dossier, outline_context,
                                  covered, segments, seg, seg_dir)
            job.set_chapter(seg_id, status="auditing")
            text = _audit_segment(cfg, llm, job, dossier, seg, text, seg_dir)
            text = _polish_segment(cfg, llm, seg_id, segments, outline, text, seg_dir)
            segments.append(text)
            covered.append(f"Segment {seg_id} — {seg.get('title', '')}: {seg.get('narrative_goal', '')}")

            job.set_chapter(seg_id, status="voicing")
            job.update(status="voicing", message=f"Voicing chapter {seg_id}")
            mp3 = _voice_segment(tts, seg_id, text, audio_dir)
            segment_audio.append(mp3)
            job.set_chapter(seg_id, status="done",
                            audio=f"/api/episodes/{job.state['id']}/segments/{seg_id}.mp3")

        job.update(status="stitching", message="Stitching the final episode")
        final = _stitch(segment_audio, job.dir / "episode.mp3")
        script = "\n\n".join(segments)
        (job.dir / "03_script.txt").write_text(script)
        job.update(status="done", message="Episode ready",
                   final_audio=f"/api/episodes/{job.state['id']}/episode.mp3",
                   script_words=word_count(script))
        log(f"[job {job.state['id']}] done -> {final}")
    except Exception as e:  # noqa: BLE001
        log(f"[job {job.state.get('id')}] phase B failed: {e}")
        job.update(status="error", error=str(e), message="Generation failed")
        raise


DRY_SEGMENT = """{A}: Welcome back to the show. This is a dry-run chapter.
{B}: And the number, believe it or not, is one hundred billion dollars.
{A}: That is a lot of dollars for a test.
{B}: It really is. On to the next chapter."""


def _write_segment(cfg, llm, job, company, dossier, outline_context, covered,
                   segments, seg, seg_dir: Path) -> str:
    seg_id = int(seg["id"])
    path = seg_dir / f"segment_{seg_id:02d}.txt"
    if path.exists():
        return path.read_text()
    if DRY:
        hosts = cfg["hosts"]
        text = DRY_SEGMENT.format(A=hosts["host_a"], B=hosts["host_b"])
        path.write_text(text)
        return text
    system = load_prompt(
        "03_segment_writer.md", COMPANY=company,
        RUNTIME_MINUTES=job.state.get("runtime_minutes", cfg["episode"]["runtime_minutes"]),
        HOST_A=cfg["hosts"]["host_a"], HOST_B=cfg["hosts"]["host_b"],
        TARGET_WORDS=seg.get("target_words", 2600),
    )
    prev_tail = ("(This is the first segment — open the show cold.)" if not segments
                 else "\n".join(segments[-1].strip().splitlines()[-8:]))
    user = (
        f"RESEARCH DOSSIER:\n\n{dossier}\n\n"
        f"EPISODE CONTEXT:\n\n{outline_context}\n\n"
        f"ALREADY COVERED IN PRIOR SEGMENTS (do not repeat):\n"
        + ("\n".join(f"- {c}" for c in covered) or "- (nothing yet)")
        + f"\n\nCLOSING LINES OF THE PREVIOUS SEGMENT:\n{prev_tail}\n\n"
        f"YOUR SEGMENT BRIEF:\n\n{json.dumps(seg, indent=2)}\n\nWrite segment {seg_id} now."
    )
    text = llm.generate(system=system, user=user, max_tokens=16000)
    path.write_text(text)
    return text


def _audit_segment(cfg, llm, job, dossier, seg, text: str, seg_dir: Path) -> str:
    seg_id = int(seg["id"])
    path = seg_dir / f"segment_{seg_id:02d}_audited.txt"
    if path.exists():
        return path.read_text()
    if DRY:
        path.write_text(text)
        return text
    system = load_prompt("03b_fact_audit.md")
    for attempt in range(2):
        raw = llm.generate(
            system=system,
            user=f"RESEARCH DOSSIER:\n\n{dossier}\n\nSEGMENT TO AUDIT:\n\n{text}",
            max_tokens=8000,
        )
        try:
            audit = parse_json_lenient(raw)
        except ValueError:
            log(f"[audit] unparseable audit for segment {seg_id}; keeping text")
            break
        for issue in audit.get("issues", []):
            quote, fix = issue.get("line_quote", ""), issue.get("replacement", "")
            if quote and fix and quote in text:
                text = text.replace(quote, fix)
        (seg_dir / f"segment_{seg_id:02d}_audit.json").write_text(json.dumps(audit, indent=2))
        if audit.get("verdict") == "pass" or attempt == 1:
            break
        log(f"[audit] segment {seg_id} failed audit; rewriting once")
        issues_desc = "\n".join(f"- {i.get('problem', '')}" for i in audit.get("issues", []))
        text = llm.generate(
            system=load_prompt(
                "03_segment_writer.md",
                COMPANY=job.state["company"],
                RUNTIME_MINUTES=job.state.get("runtime_minutes", cfg["episode"]["runtime_minutes"]),
                HOST_A=cfg["hosts"]["host_a"], HOST_B=cfg["hosts"]["host_b"],
                TARGET_WORDS=seg.get("target_words", 2600),
            ),
            user=(f"RESEARCH DOSSIER:\n\n{dossier}\n\nYOUR SEGMENT BRIEF:\n\n"
                  f"{json.dumps(seg, indent=2)}\n\nYour previous draft failed fact audit "
                  f"with these problems — rewrite the segment fixing all of them:\n{issues_desc}\n\n"
                  f"PREVIOUS DRAFT:\n\n{text}"),
            max_tokens=16000,
        )
    path.write_text(text)
    return text


def _polish_segment(cfg, llm, seg_id: int, segments: list[str], outline: dict,
                    text: str, seg_dir: Path) -> str:
    path = seg_dir / f"segment_{seg_id:02d}_final.txt"
    if path.exists():
        return path.read_text()
    if DRY:
        path.write_text(text)
        return text
    tags_rule = AUDIO_TAGS_RULE if cfg["tts"].get("provider") == "elevenlabs" else ""
    system = load_prompt("04_polish.md", AUDIO_TAGS_RULE=tags_rule)
    prev_tail = ("(episode start)" if not segments
                 else "\n".join(segments[-1].strip().splitlines()[-6:]))
    next_brief = next((s for s in outline["segments"] if int(s["id"]) == seg_id + 1), None)
    next_head = (f"(next chapter brief: {next_brief.get('title')} — {next_brief.get('narrative_goal', '')})"
                 if next_brief else "(episode end)")
    polished = llm.generate(
        system=system,
        user=(f"PREVIOUS SEGMENT ENDS WITH:\n{prev_tail}\n\n"
              f"NEXT SEGMENT:\n{next_head}\n\nSEGMENT TO POLISH:\n\n{text}"),
        max_tokens=16000,
    )
    path.write_text(polished)
    return polished


def _voice_segment(tts, seg_id: int, text: str, audio_dir: Path) -> Path:
    mp3 = audio_dir / f"segment_{seg_id:02d}.mp3"
    if mp3.exists() and mp3.stat().st_size > 0:
        return mp3
    if DRY:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "1", "-c:a", "libmp3lame", str(mp3)],
            check=True, capture_output=True,
        )
        return mp3
    chunk_dir = audio_dir / f"seg_{seg_id:02d}_chunks"
    chunks = synthesize_script(tts, text, chunk_dir)
    _stitch(chunks, mp3)
    return mp3


def _stitch(parts: list[Path], out: Path) -> Path:
    concat = out.parent / f".concat_{out.stem}.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
        check=True, capture_output=True,
    )
    concat.unlink()
    return out
