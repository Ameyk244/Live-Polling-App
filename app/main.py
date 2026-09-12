from pathlib import Path

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings  # noqa: F401  (import triggers startup env validation)
from app.core.exceptions import register_exception_handlers
from app.logging_config import configure_logging
from app.routes import health, polls
from app.sockets import events  # noqa: F401  (registers socket.io event handlers)
from app.sockets import sio

configure_logging()

fastapi_app = FastAPI(title="Live Polling App")
register_exception_handlers(fastapi_app)

# Demo/local-dev only: the manual-testing frontend is opened as a local file
# (file:// origin), so REST calls need CORS allowed from anywhere. Not meant
# for production use — see CLAUDE.md's scope notes.
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(health.router)
fastapi_app.include_router(polls.router)

# Serves frontend/index.html at GET / (html=True auto-serves index.html at the
# mount root). Mounted last so it never shadows the API routes above.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
fastapi_app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
