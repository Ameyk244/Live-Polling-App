import time

from app.config import settings
from app.core.exceptions import RateLimitedError

_last_submit_at: dict[int, float] = {}


def check_submit_cooldown(participant_id: int) -> None:
    now = time.monotonic()
    last = _last_submit_at.get(participant_id)
    if last is not None and (now - last) < settings.SUBMIT_ANSWER_COOLDOWN_SECONDS:
        raise RateLimitedError("Please wait before submitting again")


def record_submit(participant_id: int) -> None:
    _last_submit_at[participant_id] = time.monotonic()
