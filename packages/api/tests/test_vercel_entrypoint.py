def test_vercel_entrypoint_serves_existing_flask_app():
    from api.index import app

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
