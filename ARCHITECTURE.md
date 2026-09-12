# Architecture

One-page overview. See `CLAUDE.md` for the original spec and `docs/CONCEPTS_APPLIED.md`
for a line-by-line concept map into the actual code.

## Diagram

```
                        ┌───────────────────────────┐
                        │   Browser (frontend/       │
                        │   index.html — static)     │
                        └─────────────┬─────────────┘
                                      │
                     ┌────────────────┴────────────────┐
                     │                                  │
                REST (fetch)                     Socket.IO (ws)
             create / read / close          join / answer / live tally
                     │                                  │
                     ▼                                  ▼
        ┌─────────────────────────────────────────────────────────┐
        │      FastAPI + python-socketio — one ASGI app            │
        │      (socketio.ASGIApp wraps the FastAPI app;             │
        │       served together, one process, one port)             │
        │                                                            │
        │   routes/*.py        sockets/events.py                    │
        │        \                  /                                │
        │         \                /                                 │
        │          services/*.py  (business logic, authz)            │
        │                 │                                          │
        │          repositories/*.py  (only layer touching the DB)   │
        └───────────────────────────┬───────────────────────────────┘
                                     │  SQLAlchemy (ORM, no raw SQL)
                                     ▼
                        ┌───────────────────────────┐
                        │   Postgres (Supabase)      │
                        │   — or SQLite locally       │
                        └───────────────────────────┘
```

REST and Socket.IO are two parallel entry points into the *same* service/repository
layer underneath — neither talks to the database directly, and neither bypasses the
other's business rules.

## Layered architecture

Every request or event flows through the same four layers: **route/socket handler**
(parses input, calls one service method, returns/emits the result) → **Pydantic
validation** (every REST body and every socket payload, no exceptions) → **service**
(business logic and authorization decisions) → **repository** (the only code that
touches a SQLAlchemy session). The point of keeping this strict is that the two
transports — REST and Socket.IO — end up sharing identical business logic and
validation discipline instead of each growing its own ad hoc rules; a bug fix or an
authorization check in the service layer automatically protects both.

## REST vs. Socket.IO split

REST handles anything that's a one-shot request/response with no need for a live
connection: creating a poll, reading a poll or its results, and the host closing a poll.
These map naturally onto HTTP verbs and status codes, and a REST client (curl, a test
suite, a future admin tool) doesn't need to hold a socket open just to create a poll.
Socket.IO handles anything that's inherently about a *live, ongoing* room: joining a
poll (so the room can broadcast to you), submitting an answer (so everyone in the room
sees the tally move), and the live tally/close broadcasts themselves. Trying to do
either of these over plain REST would mean polling for updates; trying to do poll
creation over a socket would mean holding a connection open for something that's really
just a single request.

## Deviations from the original plan

- **Volatile events**: the plan called for `tally_update` to be a "volatile" broadcast
  (latest-value-only, no delivery guarantee). `python-socketio`'s Python server has no
  `volatile` emit parameter at all — that's a JS-client-only concept. Worked around with
  a plain fire-and-forget `emit()`; functionally equivalent here since no acknowledgement
  was ever requested on that broadcast anyway.
- **Connection state recovery**: scoped as a nice-to-have, not implemented. A
  disconnect/reconnect gets a fresh Socket.IO session with no automatic re-sync of
  events missed while disconnected — a client has to re-`join_poll`/`join_as_host` to
  get back to a known state.
- **Socket.IO namespaces**: everything runs on the default `/` namespace. A single
  namespace was sufficient at this scale (two roles, one event set); splitting host and
  participant traffic into separate namespaces would add ceremony without changing any
  actual behavior here.

## How this would scale

Not implemented, but worth naming plainly: this app currently holds two kinds of
in-process state that only work correctly on a single instance — the Socket.IO
server's room/connection state, and the in-memory rate limiter
(`app/core/rate_limiter.py`). Running more than one instance behind a load balancer
would require a **Socket.IO message-queue adapter (e.g. Redis)** so that a broadcast
emitted from the instance that received a `submit_answer` reaches clients connected to
a *different* instance in the same room. If the deployment ever falls back to HTTP
long-polling instead of WebSockets, it would also need **sticky sessions** (routing a
given client to the same instance across requests), since a polling client's session
state lives on whichever instance it first connected to. The rate limiter would need to
move to something shared (Redis again, most likely) for the same reason — an
in-process dict on one instance doesn't see submissions handled by another.
