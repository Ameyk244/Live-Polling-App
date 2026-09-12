def test_close_poll_authorization(client):
    create_resp = client.post(
        "/polls", json={"question": "Q1?", "options": ["A", "B"]}
    )
    assert create_resp.status_code == 200
    code = create_resp.json()["code"]
    host_token = create_resp.json()["host_token"]

    # A second, unrelated poll gives us a *valid but foreign* host token.
    other_resp = client.post(
        "/polls", json={"question": "Q2?", "options": ["C", "D"]}
    )
    assert other_resp.status_code == 200
    foreign_token = other_resp.json()["host_token"]

    # No token at all: HTTPBearer rejects before our handler runs.
    no_auth = client.post(f"/polls/{code}/close")
    assert no_auth.status_code in (401, 403)

    # Well-formed token, but for a different poll: our own auth check must
    # reject this with 401 (UnauthorizedError).
    wrong_auth = client.post(
        f"/polls/{code}/close",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert wrong_auth.status_code == 401

    # The poll must remain open after both rejected attempts.
    still_open = client.get(f"/polls/{code}")
    assert still_open.json()["status"] == "open"

    # Correct host token succeeds and actually flips status to closed.
    ok = client.post(
        f"/polls/{code}/close",
        headers={"Authorization": f"Bearer {host_token}"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "closed"

    persisted = client.get(f"/polls/{code}")
    assert persisted.json()["status"] == "closed"
