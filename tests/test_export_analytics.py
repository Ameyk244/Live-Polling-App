import csv
import io

from app.database import SessionLocal
from app.repositories import answer_repository, participant_repository


def _seed_participants_and_answers(code: str, poll_json: dict, num_joined: int, num_answered: int):
    """Directly seed participants/answers via the repository layer (bypassing
    sockets) so this REST-only test can set up known analytics numbers
    without spinning up a live Socket.IO server."""
    option_ids = [opt["id"] for opt in poll_json["poll"]["options"]]
    db = SessionLocal()
    try:
        poll_id = poll_json["poll"]["id"]
        participants = [
            participant_repository.create_participant(db, poll_id, f"P{i}")
            for i in range(num_joined)
        ]
        for i in range(num_answered):
            answer_repository.create_answer(
                db, poll_id, participants[i].id, option_ids[i % len(option_ids)]
            )
    finally:
        db.close()


def test_export_and_analytics_host_only_enforcement(client):
    create_resp = client.post("/polls", json={"question": "Q?", "options": ["A", "B"]})
    assert create_resp.status_code == 200
    code = create_resp.json()["code"]
    host_token = create_resp.json()["host_token"]

    other_resp = client.post("/polls", json={"question": "Other?", "options": ["C", "D"]})
    foreign_token = other_resp.json()["host_token"]

    # No token at all.
    assert client.get(f"/polls/{code}/export").status_code in (401, 403)
    assert client.get(f"/polls/{code}/analytics").status_code in (401, 403)

    # Valid host token, but for a different poll -- must be rejected, not
    # just "any host role token accepted".
    wrong_export = client.get(
        f"/polls/{code}/export", headers={"Authorization": f"Bearer {foreign_token}"}
    )
    assert wrong_export.status_code == 401
    wrong_analytics = client.get(
        f"/polls/{code}/analytics", headers={"Authorization": f"Bearer {foreign_token}"}
    )
    assert wrong_analytics.status_code == 401

    # Correct host token succeeds for both.
    ok_export = client.get(
        f"/polls/{code}/export", headers={"Authorization": f"Bearer {host_token}"}
    )
    assert ok_export.status_code == 200
    ok_analytics = client.get(
        f"/polls/{code}/analytics", headers={"Authorization": f"Bearer {host_token}"}
    )
    assert ok_analytics.status_code == 200


def test_export_formats_and_analytics_numbers(client):
    create_resp = client.post(
        "/polls", json={"question": "Pick one", "options": ["Red", "Blue"]}
    )
    poll_json = create_resp.json()
    code = poll_json["code"]
    host_token = poll_json["host_token"]

    # 3 participants joined, 2 of them answered.
    _seed_participants_and_answers(code, poll_json, num_joined=3, num_answered=2)

    headers = {"Authorization": f"Bearer {host_token}"}

    # JSON export (default format).
    json_resp = client.get(f"/polls/{code}/export", headers=headers)
    assert json_resp.status_code == 200
    body = json_resp.json()
    assert body["question"] == "Pick one"
    assert body["total_votes"] == 2
    assert {opt["vote_count"] for opt in body["options"]} == {1, 1}

    # CSV export.
    csv_resp = client.get(f"/polls/{code}/export?format=csv", headers=headers)
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(csv_resp.text)))
    data_rows = [r for r in rows if r and not r[0].startswith("#")]
    assert data_rows[0] == ["option_text", "vote_count"]
    assert len(data_rows) == 3  # header + 2 options

    # Unrecognized format falls back to json, not a 422.
    fallback_resp = client.get(f"/polls/{code}/export?format=xml", headers=headers)
    assert fallback_resp.status_code == 200
    assert fallback_resp.headers["content-type"].startswith("application/json")

    # Analytics numbers.
    analytics_resp = client.get(f"/polls/{code}/analytics", headers=headers)
    assert analytics_resp.status_code == 200
    analytics = analytics_resp.json()
    assert analytics["participants_joined"] == 3
    assert analytics["participants_answered"] == 2
    assert round(analytics["response_rate_percent"], 2) == round(2 / 3 * 100, 2)
    assert analytics["seconds_to_first_vote"] is not None
    assert analytics["seconds_to_last_vote"] is not None

    # Never exposes a per-participant display_name -> option mapping.
    assert "display_name" not in analytics_resp.text
    assert "display_name" not in json_resp.text
