import os
import socket
import threading
import time
from pathlib import Path

import pytest

# --- Test environment setup -------------------------------------------------
# Must happen BEFORE any `app.*` module is imported, since app.config.settings
# is loaded eagerly at import time (see app/config.py). Using a real on-disk
# sqlite file (not ':memory:') so that the FastAPI TestClient (in-process) and
# the live uvicorn server used for socket tests (background thread) both see
# the same data.
TEST_DB_PATH = Path(__file__).parent / "test_polling.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-key-do-not-use-in-prod"

from fastapi.testclient import TestClient  # noqa: E402
import uvicorn  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app as socket_asgi_app  # noqa: E402
from app.main import fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    Base.metadata.create_all(engine)
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Start every test with empty tables so tests don't leak state into
    each other (e.g. poll counts, generated codes)."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client():
    """A synchronous REST client wired to the real app + test DB."""
    return TestClient(fastapi_app)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server():
    """Runs the real Socket.IO+FastAPI ASGI app on a background thread with
    an actual TCP port, since python-socketio's AsyncServer has no in-process
    test client (that's a JS-client concept) — a real handshake needs a real
    HTTP/WebSocket server to connect to."""
    port = _free_port()
    config = uvicorn.Config(
        socket_asgi_app, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("test server did not start in time")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
