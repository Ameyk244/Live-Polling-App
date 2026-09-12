import pytest
import socketio


@pytest.mark.asyncio
async def test_join_poll_then_submit_answer_broadcasts_tally_update(client, live_server):
    create_resp = client.post(
        "/polls",
        json={"question": "Favorite color?", "options": ["Red", "Blue"]},
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
        assert "token" in join_ack
        token = join_ack["token"]

        submit_ack = await sio_client.call(
            "submit_answer", {"token": token, "option_id": option_id}
        )
        assert submit_ack == {"status": "ok"}

        event_name, tally = await sio_client.receive(timeout=5)
        assert event_name == "tally_update"

        matching = next(t for t in tally if t["option_id"] == option_id)
        assert matching["count"] == 1
    finally:
        await sio_client.disconnect()
