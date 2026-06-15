from api.index import app


def test_shared_trace_renders_public_viewer():
    payload = {
        "run": {
            "name": "cv_demo",
            "status": "ok",
            "started_at": "2026-06-16T00:00:00",
            "ended_at": "2026-06-16T00:00:01",
        },
        "spans": [],
    }
    client = app.test_client()

    share = client.post("/v1/share", json=payload)
    trace_id = share.get_json()["id"]

    viewer = client.get(f"/t/{trace_id}")
    embed = client.get(f"/t/{trace_id}/embed")

    assert viewer.status_code == 200
    assert embed.status_code == 200
    assert f"TRACE-{trace_id}".encode() in viewer.data
