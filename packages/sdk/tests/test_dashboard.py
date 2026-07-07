"""Flask test-client tests for the local dashboard."""
import pytest

from glasspipe._demo import seed_demo_traces


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLASSPIPE_DB_PATH", str(tmp_path / "dash.db"))
    # The seeder sleeps to shape realistic waterfalls; tests don't need that.
    import glasspipe._demo as demo_mod
    monkeypatch.setattr(demo_mod.time, "sleep", lambda _s: None)
    seed_demo_traces()
    from glasspipe._dashboard import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _run_ids(client):
    from glasspipe.storage import get_session, Run
    from sqlalchemy import select

    with get_session() as session:
        return [r.id for r in session.execute(select(Run)).scalars().all()]


def test_index_renders_full_page(client):
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in html
    assert "research_agent" in html


def test_index_htmx_poll_returns_partial(client):
    resp = client.get("/", headers={"HX-Request": "true"})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in html
    assert 'id="runs-container"' in html


def test_version_filter_and_badges(client):
    html = client.get("/").get_data(as_text=True)
    assert "version-chip" in html
    assert "v1.2.0" in html and "v1.3.0" in html

    filtered = client.get("/?version=v1.2.0").get_data(as_text=True)
    assert "v1.2.0" in filtered
    # support_agent runs are untagged, so they disappear under the filter
    assert "support_agent" not in filtered


def test_delete_run_returns_partial_not_full_page(client):
    ids = _run_ids(client)
    resp = client.delete(f"/runs/{ids[0]}")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in html
    assert 'id="runs-container"' in html
    assert ids[0] not in html


def test_clear_runs_returns_empty_state_partial(client):
    resp = client.post("/runs/clear")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in html
    assert "No traces yet" in html
    assert _run_ids(client) == []


def test_run_cost_ticker_never_rearms_load_trigger(client):
    """A 'load' trigger on the re-armed ticker would re-fire on every swap and
    turn polling into a request loop — the response must use 'every 4s' only."""
    from glasspipe.storage import get_session, Run
    from sqlalchemy import select, update

    ids = _run_ids(client)
    with get_session() as session:
        session.execute(update(Run).where(Run.id == ids[0]).values(status="running"))
        session.commit()

    html = client.get(f"/run-cost/{ids[0]}").get_data(as_text=True)
    assert 'hx-trigger="every 4s"' in html
    assert "load" not in html


def test_run_detail_and_span_detail(client):
    ids = _run_ids(client)
    detail = client.get(f"/run/{ids[0]}").get_data(as_text=True)
    assert "TIMELINE" in detail

    from glasspipe.storage import get_session, Span
    from sqlalchemy import select

    with get_session() as session:
        span_id = session.execute(
            select(Span.id).where(Span.run_id == ids[0])
        ).scalars().first()
    resp = client.get(f"/span/{span_id}")
    assert resp.status_code == 200


def test_share_preview_renders(client):
    ids = _run_ids(client)
    resp = client.get(f"/share/preview/{ids[0]}")
    assert resp.status_code == 200
    assert "Review before sharing" in resp.get_data(as_text=True)


def test_share_confirm_mock_shows_url_and_delete_token(client, monkeypatch):
    monkeypatch.setenv("GLASSPIPE_SHARE_API", "mock")
    ids = _run_ids(client)
    html = client.post(f"/share/confirm/{ids[0]}").get_data(as_text=True)
    assert "glasspipe.dev/t/" in html
    assert "Delete token" in html


def test_demo_seeder_creates_expected_runs(client):
    from glasspipe.storage import get_session, Run
    from sqlalchemy import select

    with get_session() as session:
        runs = session.execute(select(Run)).scalars().all()
    names = sorted(r.name for r in runs)
    assert names == ["research_agent", "research_agent", "support_agent", "support_agent"]
    assert any(r.status == "error" for r in runs)
    versions = {r.agent_version for r in runs}
    assert {"v1.2.0", "v1.3.0"} <= versions
