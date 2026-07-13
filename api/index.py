"""Vercel serverless shell — serves the password gate and API surface.

Episode generation requires a persistent worker (20-60 min jobs, ffmpeg, disk),
which serverless cannot run: those endpoints return a clear 503 here. The full
app lives in src/webapp.py and runs with `uvicorn src.webapp:app` on a
persistent machine (see README -> Production deploy).
"""

import asyncio
import hashlib
import hmac
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
AUTH_COOKIE = "dd_auth"

WORKER_MSG = (
    "This deployment serves the app, but episode generation needs the persistent "
    "worker (long-running jobs + audio processing), which is not attached yet. "
    "See README → Production deploy."
)


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
        await asyncio.sleep(0.8)
        raise HTTPException(401, "Wrong password")
    resp = JSONResponse({"ok": True})
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie(AUTH_COOKIE, _auth_token(), max_age=60 * 60 * 24 * 30,
                    httponly=True, samesite="lax", secure=https)
    return resp


@app.get("/api/health")
def health():
    return {"ok": True, "worker": False}


@app.get("/api/episodes")
def list_episodes():
    return []


@app.post("/api/episodes")
async def create_episode(request: Request):
    raise HTTPException(503, WORKER_MSG)


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str):
    raise HTTPException(404, "Episode not found")


@app.post("/api/episodes/{episode_id}/approve")
async def approve(episode_id: str, payload: dict):
    raise HTTPException(503, WORKER_MSG)
