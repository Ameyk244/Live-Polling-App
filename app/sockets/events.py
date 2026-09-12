import logging

from pydantic import ValidationError as PydanticValidationError
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import AppError, ValidationError
from app.database import SessionLocal
from app.schemas.answer import SubmitAnswerPayload
from app.schemas.participant import JoinAsHostPayload, JoinPollPayload
from app.services import answer_service, auth_service, poll_service
from app.sockets import sio

logger = logging.getLogger(__name__)

# In-memory only, per-process, not distributed across workers — same caveat as
# app/core/rate_limiter.py. Tracks which participant socket ids are currently
# connected to each poll's room, purely for live presence display (not persisted).
_participant_sids: dict[str, set[str]] = {}


async def _broadcast_participant_count(poll_code: str) -> None:
    count = len(_participant_sids.get(poll_code, set()))
    await sio.emit("participant_count", {"count": count}, room=poll_code)


def _poll_payload(poll) -> dict:
    return {
        "id": poll.id,
        "code": poll.code,
        "question": poll.question,
        "status": poll.status,
        "expires_at": poll.expires_at.isoformat() if poll.expires_at else None,
        "options": [
            {"id": o.id, "text": o.text, "position": o.position} for o in poll.options
        ],
    }


def _tally_payload(tally) -> list[dict]:
    return [t.model_dump() for t in tally]


@sio.on("join_poll")
async def join_poll(sid, raw_payload):
    db = SessionLocal()
    try:
        try:
            payload = JoinPollPayload.model_validate(raw_payload)
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc

        poll, participant, token = await poll_service.join_poll(
            db, poll_code=payload.poll_code, display_name=payload.display_name
        )
        tally = await run_in_threadpool(poll_service.get_tally, db, poll.id)

        await sio.enter_room(sid, poll.code)

        _participant_sids.setdefault(poll.code, set()).add(sid)
        await sio.save_session(sid, {"poll_code": poll.code, "role": "participant"})
        await _broadcast_participant_count(poll.code)

        poll_payload = _poll_payload(poll)
        return {
            "token": token,
            "participant_id": participant.id,
            "poll": poll_payload,
            "options": poll_payload["options"],
            "tally": _tally_payload(tally),
        }
    except AppError as e:
        await sio.emit("error", {"code": e.code, "message": e.message}, to=sid)
    except Exception:
        logger.exception("unhandled error in join_poll")
        await sio.emit(
            "error", {"code": "internal_error", "message": "Something went wrong"}, to=sid
        )
    finally:
        db.close()


@sio.on("disconnect")
async def disconnect(sid):
    try:
        session = await sio.get_session(sid)
    except Exception:
        return
    if session.get("role") == "participant":
        poll_code = session.get("poll_code")
        if poll_code:
            _participant_sids.get(poll_code, set()).discard(sid)
            await _broadcast_participant_count(poll_code)


@sio.on("join_as_host")
async def join_as_host(sid, raw_payload):
    db = SessionLocal()
    try:
        try:
            payload = JoinAsHostPayload.model_validate(raw_payload)
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc

        poll, _claims = await poll_service.join_as_host(db, payload.token)
        tally = await run_in_threadpool(poll_service.get_tally, db, poll.id)

        await sio.enter_room(sid, poll.code)

        return {
            "poll": _poll_payload(poll),
            "tally": _tally_payload(tally),
        }
    except AppError as e:
        await sio.emit("error", {"code": e.code, "message": e.message}, to=sid)
    except Exception:
        logger.exception("unhandled error in join_as_host")
        await sio.emit(
            "error", {"code": "internal_error", "message": "Something went wrong"}, to=sid
        )
    finally:
        db.close()


@sio.on("submit_answer")
async def submit_answer(sid, raw_payload):
    db = SessionLocal()
    try:
        try:
            payload = SubmitAnswerPayload.model_validate(raw_payload)
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc

        claims = auth_service.authorize_participant(payload.token)

        result = await answer_service.submit_answer(
            db,
            poll_id=claims.poll_id,
            participant_id=claims.participant_id,
            option_id=payload.option_id,
        )

        # NOTE: python-socketio's server API has no "volatile" emit flag (that is a
        # JS Socket.IO client/server-only concept); a plain room broadcast with no
        # ack callback already behaves as fire-and-forget / latest-value-only here.
        await sio.emit(
            "tally_update",
            _tally_payload(result.tally),
            room=result.poll_code,
        )

        return {"status": "ok"}
    except AppError as e:
        await sio.emit("error", {"code": e.code, "message": e.message}, to=sid)
    except Exception:
        logger.exception("unhandled error in submit_answer")
        await sio.emit(
            "error", {"code": "internal_error", "message": "Something went wrong"}, to=sid
        )
    finally:
        db.close()
