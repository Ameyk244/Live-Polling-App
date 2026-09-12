from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import jwt
from pydantic import BaseModel

from app.config import settings
from app.core.exceptions import UnauthorizedError


class HostTokenPayload(BaseModel):
    poll_id: int
    role: Literal["host"]


class ParticipantTokenPayload(BaseModel):
    poll_id: int
    participant_id: int
    role: Literal["participant"]


def create_host_token(poll_id: int) -> str:
    payload = {
        "poll_id": poll_id,
        "role": "host",
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.HOST_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_participant_token(poll_id: int, participant_id: int) -> str:
    payload = {
        "poll_id": poll_id,
        "participant_id": participant_id,
        "role": "participant",
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.PARTICIPANT_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc


def verify_host_token(token: str, expected_poll_id: Optional[int] = None) -> HostTokenPayload:
    data = _decode(token)
    try:
        claims = HostTokenPayload.model_validate(data)
    except Exception as exc:
        raise UnauthorizedError("Invalid token claims") from exc
    if expected_poll_id is not None and claims.poll_id != expected_poll_id:
        raise UnauthorizedError("Token does not match this poll")
    return claims


def verify_participant_token(
    token: str, expected_poll_id: Optional[int] = None
) -> ParticipantTokenPayload:
    data = _decode(token)
    try:
        claims = ParticipantTokenPayload.model_validate(data)
    except Exception as exc:
        raise UnauthorizedError("Invalid token claims") from exc
    if expected_poll_id is not None and claims.poll_id != expected_poll_id:
        raise UnauthorizedError("Token does not match this poll")
    return claims
