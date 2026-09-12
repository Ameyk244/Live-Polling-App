# Live Polling App

A minimal live-polling backend: FastAPI (REST) + python-socketio (real-time), SQLAlchemy
+ Alembic, JWT-based host/participant auth, served together with a small static
frontend. See `CLAUDE.md` for the full spec this was built against, and
`ARCHITECTURE.md` for a one-page overview of how the pieces fit together.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

copy .env.example .env    # Windows
# cp .env.example .env    # macOS/Linux
```

Then edit `.env`:

- `DATABASE_URL` — a Postgres connection string is the primary/expected setup, e.g. a
  free [Supabase](https://supabase.com) project's "Session pooler" connection string:
  ```
  DATABASE_URL=postgresql://<user>:<password>@<host>:5432/postgres
  ```
  If you'd rather not set up a hosted database, a local SQLite file works as a simpler
  fallback and needs no external service:
  ```
  DATABASE_URL=sqlite:///./polling.db
  ```
  Both are supported with zero code changes — SQLAlchemy handles the difference.
- `JWT_SECRET` — a real random secret, not the placeholder. Generate one with:
  ```bash
  ./.venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(32))"
  ```

Then run the migration and start the server:

```bash
alembic upgrade head

uvicorn app.main:app --reload
```

The app is now accessible directly at **http://127.0.0.1:8000/** — the frontend is
served from that same URL (no separate HTML file to open). REST endpoints are under
`/polls` and `/health`; Socket.IO is mounted on the same ASGI app at `/socket.io`.

## Frontend

A single-page, role-separated demo UI (`frontend/index.html`, plain HTML/CSS/JS, no
build step) served directly by the backend:

- **Landing** (`/`) — choose "Create a Poll" or "Join a Poll".
- **Host view** (`#host/{code}`) — poll code, live tally, Close Poll button. Reached
  only right after creating a poll in that browser session (a host token can't be
  reconstructed from the URL alone; a direct/refreshed load shows a graceful
  "session not found" message instead of erroring).
- **Participant view** (`#join/{code}`) — question, answer buttons, submitted/error
  state. Same in-session caveat as the host view.

Open two tabs — one via "Create a Poll", one via "Join a Poll" with the resulting
code — to see the live flow end to end.

## REST endpoints

- `POST /polls` — `{question, options: [str, ...]}` -> `{code, host_token, poll}`
- `GET /polls/{code}` — poll question/options/status
- `GET /polls/{code}/results` — current answer tally per option
- `POST /polls/{code}/close` — `Authorization: Bearer <host_token>`, closes the poll and
  broadcasts `poll_closed` to the poll's room
- `GET /health` — checks DB connectivity

## Socket.IO events

- `join_poll` `{poll_code, display_name}` — no token required; issues a participant
  token and joins the room named after the poll code
- `join_as_host` `{token}` — verifies the host token and joins the room so the host can
  observe live updates
- `submit_answer` `{token, option_id}` — verifies the participant token, applies
  business rules (poll open, valid option, not already answered, rate-limit cooldown),
  persists the answer, then acks the sender and broadcasts `tally_update` to the room
- `error` `{code, message}` — emitted to the sender only, on any failure in any of the
  above

## Out of scope

This is an easy-to-moderate learning project, not a production system. The following
are intentionally not implemented:

- Redis adapter / multi-instance Socket.IO scaling
- Distributed tracing
- Caching layers
- Complex RBAC (only the two flat roles `host` / `participant` exist)
- Socket.IO connection state recovery (a disconnect/reconnect gets a fresh connection,
  no automatic re-sync of missed events)
- "Volatile" broadcasts as originally planned — `python-socketio`'s Python server has
  no `volatile` emit flag at all (it's a JS-client-only concept); `tally_update` is a
  plain fire-and-forget broadcast instead, which is functionally equivalent here since
  no acknowledgement was ever requested on it. See `ARCHITECTURE.md` for details.

## Tests

```bash
pytest
```
