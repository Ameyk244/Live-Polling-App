from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.poll import Poll


def test_create_poll_with_invalid_body_returns_422_and_skips_service(client):
    # Only one option: CreatePollRequest requires min_length=2, so this should
    # fail Pydantic validation before the request handler's body ever calls
    # poll_service.create_poll.
    response = client.post(
        "/polls",
        json={"question": "Favorite color?", "options": ["OnlyOneOption"]},
    )

    assert response.status_code == 422

    db = SessionLocal()
    try:
        poll_count = db.execute(select(func.count()).select_from(Poll)).scalar_one()
    finally:
        db.close()

    # If the service layer had been reached, a poll row would exist.
    assert poll_count == 0
