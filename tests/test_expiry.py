from datetime import datetime, timedelta

import pytest
import socketio

from app.database import SessionLocal
from app.models.poll import Poll


def _backdate_expiry(code: str) -> None:
    """Force a poll's expires_at into the past directly via the DB, so the
    test doesn't have to actually wait out a real duration."""
    db = SessionLocal()
    try:
        poll = db.query(Poll).filter(Poll.code == code).one()
        poll.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()


def test_expired_poll_auto_closes_on_next_get(client):
    create_resp = client.post(
        "/polls",
        json={"question": "Expiry test?", "options": ["A", "B"], "duration_minutes": 60},
    )
    assert create_resp.status_code == 200
    code = create_resp.json()["code"]
    assert create_resp.json()["poll"]["status"] == "open"

    _backdate_expiry(code)

    # Lazy check: expiry takes effect on the next real read of the poll.
    get_resp = client.get(f"/polls/{code}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_submit_answer_rejected_after_poll_expires(client, live_server):
    create_resp = client.post(
        "/polls",
        json={"question": "Expiry vs submit?", "options": ["A", "B"], "duration_minutes": 60},
    )
    assert create_resp.status_code == 200
    body = create_resp.json()
    code = body["code"]
    option_id = body["poll"]["options"][0]["id"]

    sio_client = socketio.AsyncSimpleClient()
    await sio_client.connect(live_server, transports=["websocket"])
    try:
        join_ack = await sio_client.call(
            "join_poll", {"poll_code": code, "display_name": "Alice"}
        )
        token = join_ack["token"]

        # Poll expires only after the participant already has a valid token —
        # mirrors a real participant who joined before the timer ran out.
        _backdate_expiry(code)

        submit_ack = await sio_client.call(
            "submit_answer", {"token": token, "option_id": option_id}
        )
        assert submit_ack is None or submit_ack == {}

        # The participant is in the room, so expiry detection's own
        # poll_closed broadcast (fired inside enforce_expiry) arrives too —
        # possibly before the "error" ack for the rejected submit_answer.
        # Drain until we see "error"; only "poll_closed" should precede it.
        seen = []
        for _ in range(5):
            event_name, payload = await sio_client.receive(timeout=5)
            if event_name == "error":
                assert payload["code"] == "poll_closed"
                break
            seen.append(event_name)
        else:
            raise AssertionError(f"never received 'error' event; saw: {seen}")
        assert all(ev == "poll_closed" for ev in seen)
    finally:
        await sio_client.disconnect()
