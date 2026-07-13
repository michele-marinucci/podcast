"""Web app: type a ticker, upload documents, approve the outline, get an episode.

Run:
    uvicorn src.webapp:app --reload            # http://localhost:8000
    DRY_RUN=1 uvicorn src.webapp:app           # full flow, canned content, no API keys
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .pipeline import Job, create_job, resume_after_approval, run_until_checkpoint

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
ALLOWED_UPLOADS = {".pdf", ".docx", ".txt", ".md"}

# Shared-password gate: set APP_PASSWORD to require login for all /api/ routes.
# Leave unset for open local development.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
AUTH_COOKIE = "dd_auth"


def _auth_token() -> str:
    return hashlib.sha256(f"deep-dives:{APP_PASSWORD}".encode()).hexdigest()


app = FastAPI(title="Deep Dives")


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if APP_PASSWORD and path.startswith("/api/") and path not in ("/api/login", "/api/health"):
        cookie = request.cookies.get(AUTH_COOKIE, "")
        if not hmac.compare_digest(cookie, _auth_token()):
            return JSONResponse({"detail": "Password required"}, status_code=401)
    return await call_next(request)


@app.post("/api/login")
async def login(payload: dict, request: Request):
    if not APP_PASSWORD:
        return {"ok": True}
    if not hmac.compare_digest(str(payload.get("password", "")), APP_PASSWORD):
        await asyncio.sleep(0.8)  # slow brute force
        raise HTTPException(401, "Wrong password")
    resp = JSONResponse({"ok": True})
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(AUTH_COOKIE, _auth_token(), max_age=60 * 60 * 24 * 30,
                    httponly=True, samesite="lax", secure=https)
    return resp


def _job(episode_id: str) -> Job:
    job_dir = OUTPUT / episode_id
    if not (job_dir / "state.json").exists():
        raise HTTPException(404, "Episode not found")
    return Job(job_dir)


@app.get("/api/health")
def health():
    return {"ok": True}


def _require_worker() -> None:
    """Generation runs in-process: it needs a persistent machine with ffmpeg and
    disk. On serverless (Vercel), background threads are killed after the response
    and the filesystem is read-only — so creation is guarded off, not broken."""
    if os.environ.get("VERCEL"):
        raise HTTPException(
            503,
            "This deployment serves the app, but episode generation needs the "
            "persistent worker (long-running jobs + audio processing). "
            "See README → Production deploy.",
        )


ACTIVE_STATUSES = {"queued", "researching", "fetching", "drafting_outline",
                   "writing", "voicing", "stitching"}
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "2"))


def _active_jobs() -> int:
    count = 0
    if OUTPUT.is_dir():
        for state_path in OUTPUT.glob("*/state.json"):
            try:
                if json.loads(state_path.read_text()).get("status") in ACTIVE_STATUSES:
                    count += 1
            except json.JSONDecodeError:
                continue
    return count


@app.post("/api/episodes")
async def create_episode(
    company: str = Form(...),
    runtime: int = Form(210),
    preferences: str = Form(""),
    doc_types: str = Form("[]"),  # JSON: [{"file": name, "doc_type": ..., "period": ...}]
    files: list[UploadFile] = File(default=[]),
):
    company = company.strip()
    if not company:
        raise HTTPException(400, "Company name or ticker is required")
    _require_worker()
    if _active_jobs() >= MAX_ACTIVE_JOBS:
        raise HTTPException(429, "Too many episodes generating right now — try again in a few minutes")

    upload_names = []
    job = create_job(company, runtime, preferences, [])
    uploads_dir = job.dir / "uploads"
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in ALLOWED_UPLOADS:
            continue
        dest = uploads_dir / Path(f.filename).name
        dest.write_bytes(await f.read())
        upload_names.append(dest.name)
    try:
        manifest = json.loads(doc_types)
        if isinstance(manifest, list) and manifest:
            (uploads_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    except json.JSONDecodeError:
        pass
    job.update(uploads=upload_names)

    threading.Thread(target=run_until_checkpoint, args=(job,), daemon=True).start()
    return {"id": job.state["id"]}


@app.get("/api/episodes")
def list_episodes():
    episodes = []
    if OUTPUT.is_dir():
        for state_path in sorted(OUTPUT.glob("*/state.json"),
                                 key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                s = json.loads(state_path.read_text())
            except json.JSONDecodeError:
                continue
            episodes.append({k: s.get(k) for k in
                             ("id", "company", "status", "episode_title", "created_at")})
    return episodes


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str):
    return JSONResponse(_job(episode_id).state)


@app.post("/api/episodes/{episode_id}/approve")
async def approve(episode_id: str, payload: dict):
    job = _job(episode_id)
    if job.state.get("status") != "awaiting_approval":
        raise HTTPException(409, f"Episode is {job.state.get('status')}, not awaiting approval")
    _require_worker()
    if _active_jobs() >= MAX_ACTIVE_JOBS:
        raise HTTPException(429, "Too many episodes generating right now — approve again in a few minutes")
    job.update(status="writing", message="Approved — writing the episode")
    notes = {str(k): v for k, v in (payload.get("notes") or {}).items() if v}
    global_note = (payload.get("global_note") or "").strip()
    threading.Thread(
        target=resume_after_approval, args=(job, notes, global_note), daemon=True
    ).start()
    return {"ok": True}


@app.get("/api/episodes/{episode_id}/segments/{seg_id}.mp3")
def segment_audio(episode_id: str, seg_id: int):
    path = OUTPUT / episode_id / "audio" / f"segment_{seg_id:02d}.mp3"
    if not path.exists():
        raise HTTPException(404, "Segment audio not ready")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/episodes/{episode_id}/episode.mp3")
def episode_audio(episode_id: str):
    path = OUTPUT / episode_id / "episode.mp3"
    if not path.exists():
        raise HTTPException(404, "Episode audio not ready")
    return FileResponse(path, media_type="audio/mpeg",
                        filename=f"{episode_id}.mp3")


@app.get("/api/episodes/{episode_id}/script")
def episode_script(episode_id: str):
    path = OUTPUT / episode_id / "03_script.txt"
    if not path.exists():
        raise HTTPException(404, "Script not ready")
    return FileResponse(path, media_type="text/plain")


# Local/container serving of the frontend. On Vercel, web/ is served by the
# platform's static routing instead (see vercel.json) and may be absent here.
if (ROOT / "web").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
