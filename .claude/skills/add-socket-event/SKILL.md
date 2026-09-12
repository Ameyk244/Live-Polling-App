---
name: add-socket-event
description: Repeatable pattern for adding a new Socket.IO event handler to the Live Polling App — validate payload, check room/role authorization, call service layer, persist via repository if needed, emit ack/broadcast, with error-emit fallback on any failure.
---

Use this pattern for every new Socket.IO event in `app/sockets/events.py` (or a new
module under `app/sockets/` for a distinct concern). It mirrors the REST layering in
`CLAUDE.md`: handler -> validation -> service -> repository, applied to sockets.

## Steps

1. **Validate payload** — define a Pydantic model for the event's payload and parse the
   raw dict into it first. If parsing fails, emit `error` to the sender with a
   validation error code/message and return. Never let an unvalidated dict reach step 2.

2. **Check room/role authorization** — decode and verify any token in the payload
   (`app/core/security.py`). Confirm the resulting role/identity is actually allowed to
   perform this action against the poll/room in question (e.g. a participant token's
   `poll_id` must match the room being acted on; a host-only event needs `role: host`).
   Never trust the client's own claim about its role, its poll code, or that it's
   already a room member — re-derive it from the verified token every time.

3. **Call the service layer** — business logic (state checks like "poll must be open",
   "not already answered", rate-limit checks) lives in `app/services/`, not in the
   socket handler. The handler calls one service method with validated, authorized
   inputs.

4. **Persist via repository if needed** — the service calls into `app/repositories/`
   for any DB read/write. The socket handler never imports SQLAlchemy directly.

5. **Emit ack/broadcast response**:
   - Mutating events (e.g. `submit_answer`) return an explicit ack to the caller
     confirming success — this is the acknowledgement callback, not just a broadcast.
   - Broadcasts to the room use `to=room` (room name = poll code). Use
     `skip_sid=<sender>` only if the sender shouldn't get its own broadcast.
   - Frequent/latest-value-only broadcasts (e.g. `tally_update`) are sent with
     `volatile=True`. State-transition broadcasts (e.g. `poll_closed`) are not volatile.

6. **Error-emit fallback** — wrap steps 1-5 in a try/except that catches the typed
   exceptions from `app/core/exceptions.py` (invalid option, poll closed, already
   answered, unauthorized, validation error) and emits a single consistent shape back
   to the sender only:
   ```
   emit("error", {"code": "<snake_case_code>", "message": "<human readable>"}, to=sid)
   ```
   Never broadcast an error to the room, and never let an exception propagate out of
   the handler unhandled.

## Minimal shape

```python
@sio.on("submit_answer")
async def submit_answer(sid, raw_payload):
    try:
        payload = SubmitAnswerPayload.model_validate(raw_payload)   # 1. validate
        claims = verify_token(payload.token, expect_role="participant")  # 2. authorize
        result = await answer_service.submit_answer(                # 3. service
            poll_id=claims.poll_id,
            participant_id=claims.participant_id,
            option_id=payload.option_id,
        )
        await sio.emit("tally_update", result.tally, room=claims.poll_code, volatile=True)
        return {"status": "ok"}                                     # ack
    except AppError as e:
        await sio.emit("error", {"code": e.code, "message": str(e)}, to=sid)
```

(`answer_service.submit_answer` is where the repository call and business-rule checks
live — not shown here since that's step 3/4, not the handler's concern.)
