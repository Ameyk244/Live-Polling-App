from app.core.security import (
    HostTokenPayload,
    ParticipantTokenPayload,
    verify_host_token,
    verify_participant_token,
)


def authorize_host(token: str, expected_poll_id: int | None = None) -> HostTokenPayload:
    return verify_host_token(token, expected_poll_id=expected_poll_id)


def authorize_participant(
    token: str, expected_poll_id: int | None = None
) -> ParticipantTokenPayload:
    return verify_participant_token(token, expected_poll_id=expected_poll_id)
