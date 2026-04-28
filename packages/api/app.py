"""Hosted GlassPipe share API — runs on Railway, serves glasspipe.dev/t/<id>."""
import json
import os
import random
import secrets
import string
from datetime import datetime, timedelta

from flask import Flask, abort, jsonify, render_template, request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, SharedTrace

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///glasspipe_shares.db")
# Railway provides postgres:// but SQLAlchemy 2.x requires postgresql://
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

_engine = create_engine(_DATABASE_URL)


def _init_db() -> None:
    Base.metadata.create_all(_engine)


def _get_session() -> Session:
    return Session(_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_id(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def _utcnow() -> datetime:
    return datetime.utcnow()


def _ms(delta) -> float:
    return delta.total_seconds() * 1000


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    # Normalise to naive UTC (SQLite stores naive datetimes)
    if dt.tzinfo is not None:
        from datetime import timezone
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _age_string(dt: datetime) -> str:
    delta = _utcnow() - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = delta.seconds // 60
    if minutes >= 1:
        return f"{minutes}m ago"
    return "just now"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return jsonify({"service": "glasspipe-api", "status": "ok"})


@app.post("/v1/share")
def share():
    """Receive a redacted trace payload, store it, return a public URL."""
    _init_db()
    body = request.get_json(silent=True)
    if not body or "run" not in body:
        return jsonify({"error": "invalid payload — expected {run, spans}"}), 400

    now = _utcnow()
    share_id = _short_id()
    token = secrets.token_urlsafe(24)

    with _get_session() as session:
        session.add(SharedTrace(
            id=share_id,
            payload=body,
            created_at=now,
            expires_at=now + timedelta(days=30),
            delete_token=token,
            view_count=0,
        ))
        session.commit()

    return jsonify({
        "id": share_id,
        "url": f"https://glasspipe.dev/t/{share_id}",
        "delete_token": token,
    }), 201


@app.get("/v1/trace/<trace_id>")
def get_trace(trace_id):
    """Return the stored payload as JSON."""
    with _get_session() as session:
        trace = session.get(SharedTrace, trace_id)

    if trace is None:
        return jsonify({"error": "not found"}), 404
    if trace.expires_at < _utcnow():
        return jsonify({"error": "trace expired"}), 410

    return jsonify(trace.payload)


@app.get("/t/<trace_id>")
def view_trace(trace_id):
    """Public viewer page."""
    with _get_session() as session:
        trace = session.get(SharedTrace, trace_id)

    if trace is None:
        return render_template("404.html"), 404

    if trace.expires_at < _utcnow():
        return render_template("expired.html"), 410

    payload = trace.payload
    run = payload["run"]
    raw_spans = payload.get("spans", [])

    # Waterfall math — identical to local dashboard
    run_start = _parse_dt(run.get("started_at"))
    run_end   = _parse_dt(run.get("ended_at")) or _utcnow()
    run_duration_ms = max(_ms(run_end - run_start), 1.0)

    span_data = []
    for sp in raw_spans:
        sp_start = _parse_dt(sp.get("started_at"))
        sp_end   = _parse_dt(sp.get("ended_at")) or _utcnow()
        sp_dur   = max(_ms(sp_end - sp_start), 0.0)
        offset   = max(_ms(sp_start - run_start), 0.0)

        start_pct = min(offset / run_duration_ms * 100, 99.0)
        width_pct = max(sp_dur / run_duration_ms * 100, 0.5)
        width_pct = min(width_pct, 100.0 - start_pct)

        # input/output/metadata may be stored as parsed dicts OR raw JSON strings
        # depending on SDK version — handle both
        def _coerce(v):
            if v is None:
                return None
            if isinstance(v, str):
                try:
                    return json.loads(v)
                except Exception:
                    return v
            return v

        span_data.append({
            "id": sp.get("id", ""),
            "name": sp.get("name", ""),
            "kind": sp.get("kind", "custom"),
            "status": sp.get("status", "ok"),
            "duration_ms": round(sp_dur, 1),
            "start_pct": round(start_pct, 3),
            "width_pct": round(width_pct, 3),
            "input": _coerce(sp.get("input") or sp.get("input_json")),
            "output": _coerce(sp.get("output") or sp.get("output_json")),
            "metadata": _coerce(sp.get("metadata") or sp.get("metadata_json")),
        })

    # Keyed by id for JS lookup
    spans_by_id = {sp["id"]: sp for sp in span_data}

    return render_template(
        "trace_viewer.html",
        run=run,
        spans=span_data,
        spans_json=json.dumps(spans_by_id),
        run_duration_ms=round(run_duration_ms),
        share_url=f"glasspipe.dev/t/{trace_id}",
        shared_ago=_age_string(trace.created_at),
    )


if __name__ == "__main__":
    _init_db()
    app.run(host="127.0.0.1", port=5051, debug=True, use_reloader=False)
