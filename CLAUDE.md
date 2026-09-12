# Live Polling App

Learning project for backend fundamentals + Socket.IO. Scope is intentionally
easy-to-moderate: minimum real implementation of each concept below, not gold-plated.

## Stack
- FastAPI (Python) + python-socketio (ASGI, ASGIApp mounted onto the FastAPI app)
- SQLite for local dev (swap `DATABASE_URL` for Postgres later if ever needed — no
  code changes required, SQLAlchemy abstracts it)
- SQLAlchemy + Alembic for migrations
- Pydantic for validation (request bodies AND socket event payloads)
- JWT (PyJWT) for lightweight auth — no session table, no refresh tokens

## Architecture (layered, mirrored for REST and Socket.IO)
```
route / socket handler  ->  Pydantic validation  ->  service layer  ->  repository layer (DB)
```
- Routes/handlers: parse input, call one service method, return/emit the result. No
  business logic, no direct DB access here.
- Services: business logic, authorization decisions, orchestration across repositories.
- Repositories: the only layer that touches SQLAlchemy sessions/queries.
- Socket.IO event handlers follow the exact same shape as REST routes — see the
  `add-socket-event` skill for the required pattern.

## REST vs Socket.IO split
- **REST**: create poll, fetch poll by code, fetch poll results/history, host actions
  (start/close poll).
- **Socket.IO**: join a poll room, submit an answer, live tally broadcasts.

## Roles
- `host` — created the poll (gets a JWT with `role: host` at creation time).
- `participant` — joined via poll code (gets a JWT with `role: participant` on join).
- Host-only actions (e.g. closing a poll) are authorization-checked **server-side** from
  the JWT claims. Never trust a client-asserted role or poll code alone.

## Socket.IO conventions
- One room per poll session; room name = poll code.
- `submit_answer` (and other mutating events) use **acknowledgements** — the caller gets
  an explicit ack confirming the event was received and valid, or an `error` emit if not.
- Live tally broadcasts (`tally_update`) are **volatile** — latest count only, no
  guaranteed delivery of every intermediate tick. `poll_closed` broadcasts are NOT
  volatile (must be delivered reliably).
- Room membership is established server-side after validating a token/poll code —
  never trust a client's claim that it's already in a room or already authorized.

## Validation
Every REST body AND every socket event payload is validated with a Pydantic model
before touching business logic. No exceptions, no "trust the client" shortcuts.

## Error handling
- REST: one centralized exception handler (FastAPI exception handler) mapping typed
  exceptions (`app/core/exceptions.py`) to HTTP status codes.
- Socket.IO: one consistent error-emit pattern — on any failure, emit `error` with
  `{code, message}` back to the sender only (never broadcast an error).
- Must cover at minimum: invalid option selected, poll already closed, participant
  already answered, unauthorized host action.

## Must-have extras
- Startup env-var validation — fail loudly (raise, don't warn) if `DATABASE_URL` or
  `JWT_SECRET` is missing.
- `/health` endpoint that checks DB connectivity (not just "process is up").
- Basic structured logging (timestamp, level, logger name, message) at key lifecycle
  points: poll created, participant joined, answer submitted, poll closed, errors.
- Simple in-memory rate limiting on `submit_answer` (per participant cooldown) to
  prevent spam. Not distributed, not Redis-backed — in-process dict is enough here.

## DB schema (4 tables)
- `polls`: id, code (unique), question, status (open/closed), created_at, closed_at
- `poll_options`: id, poll_id (FK), text, position
- `participants`: id, poll_id (FK), display_name, joined_at
- `answers`: id, poll_id (FK), participant_id (FK), option_id (FK), created_at;
  unique (poll_id, participant_id) — one answer per participant (single-question polls).

## Testing
3-5 meaningful tests only, in `tests/`:
1. One validation test (bad REST body rejected)
2. One auth/authorization test (host-only action rejected/allowed correctly)
3. One full socket flow test (join room, submit answer, receive tally)
4-5. Optional stretch tests (duplicate answer, invalid option) if time allows.

Do not pad this with incidental coverage — these tests exist to prove the concepts
above work, not to maximize coverage.

## Explicitly out of scope
Redis adapter / multi-instance Socket.IO scaling, distributed tracing, caching layers,
complex RBAC. Noted here and in the README only — no implementation, no stub code for
these.
