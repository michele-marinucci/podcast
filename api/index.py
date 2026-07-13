"""Vercel serverless entry point — exposes the FastAPI app.

Serves the UI, auth, and read APIs. Episode *generation* requires a persistent
worker (long jobs, ffmpeg, disk) and is guarded off on serverless — see
README -> Production deploy.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.webapp import app  # noqa: E402, F401  (Vercel picks up `app` as ASGI)
