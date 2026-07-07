"""Hosted GlassPipe share API — runs on Railway, serves glasspipe.dev/t/<id>."""
import json
import logging
import os
import random
import secrets
import string
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, abort, jsonify, render_template, request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, SharedTrace

logging.basicConfig(level=logging.INFO, format="%(message)s")
_log = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///glasspipe_shares.db")
# Railway provides postgres:// but SQLAlchemy 2.x requires postgresql://
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Append sslmode to URL for Railway Postgres-SSL template
if _DATABASE_URL.startswith("postgresql://"):
    if "sslmode" not in _DATABASE_URL:
        if ".railway.internal" in _DATABASE_URL:
            _DATABASE_URL += "?sslmode=disable"
        else:
            _DATABASE_URL += "?sslmode=require"

_BASE_URL     = os.environ.get("GLASSPIPE_BASE_URL", "https://glasspipe.dev")
# Comma-separated trace ids that never expire (demo traces linked from the
# landing page and README — without this they die every TTL window).
_PINNED_IDS   = {
    t.strip() for t in os.environ.get("GLASSPIPE_PINNED_TRACES", "").split(",") if t.strip()
}
_MAX_BYTES    = int(float(os.environ.get("GLASSPIPE_MAX_PAYLOAD_MB", "5")) * 1024 * 1024)
_TTL_DAYS     = int(os.environ.get("GLASSPIPE_TRACE_TTL_DAYS", "30"))

_engine = create_engine(_DATABASE_URL)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _init_db() -> None:
    Base.metadata.create_all(_engine)


def _get_session() -> Session:
    return Session(_engine)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.before_request
def _before():
    request._t0 = time.monotonic()


@app.after_request
def _after(response):
    ms = round((time.monotonic() - request._t0) * 1000, 1)
    _log.info("%s %s %s %.1fms", request.method, request.path, response.status_code, ms)
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_id(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def _utcnow() -> datetime:
    # Naive UTC — matches how timestamps are stored (SQLite/Postgres DateTime).
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ms(delta) -> float:
    return delta.total_seconds() * 1000


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    # Normalise to naive UTC (SQLite stores naive datetimes)
    if dt.tzinfo is not None:
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

@app.get("/health")
def health():
    return jsonify({"status": "ok", "timestamp": _utcnow().isoformat()})


@app.route("/")
def index():
    return jsonify({"service": "glasspipe-api", "status": "ok"})


@app.post("/v1/share")
def share():
    """Receive a redacted trace payload, store it, return a public URL."""
    _init_db()

    # Reject oversized payloads before parsing JSON
    if request.content_length and request.content_length > _MAX_BYTES:
        mb = _MAX_BYTES // (1024 * 1024)
        return jsonify({"error": f"Payload too large (max {mb}MB)"}), 413

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
            expires_at=now + timedelta(days=_TTL_DAYS),
            delete_token=token,
            view_count=0,
        ))
        session.commit()

    return jsonify({
        "id": share_id,
        "url": f"{_BASE_URL}/t/{share_id}",
        "delete_token": token,
    }), 201


@app.get("/v1/trace/<trace_id>")
def get_trace(trace_id):
    """Return the stored payload as JSON."""
    with _get_session() as session:
        trace = session.get(SharedTrace, trace_id)

    if trace is None:
        return jsonify({"error": "not found"}), 404
    if trace_id not in _PINNED_IDS and trace.expires_at < _utcnow():
        return jsonify({"error": "trace expired"}), 410

    return jsonify(trace.payload)


@app.delete("/v1/trace/<trace_id>")
def delete_trace(trace_id):
    """Owner-initiated deletion using the delete token from POST /v1/share.

    Token via ?token=… or the X-Delete-Token header.
    """
    token = request.args.get("token") or request.headers.get("X-Delete-Token")
    if not token:
        return jsonify({"error": "missing delete token"}), 401

    with _get_session() as session:
        trace = session.get(SharedTrace, trace_id)
        if trace is None:
            return jsonify({"error": "not found"}), 404
        if not secrets.compare_digest(trace.delete_token, token):
            return jsonify({"error": "invalid delete token"}), 403
        session.delete(trace)
        session.commit()

    return jsonify({"deleted": trace_id}), 200


def _coerce_json(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _render_trace(trace_id, embed=False):
    """Shared logic for full-page and embed trace viewers."""
    with _get_session() as session:
        trace = session.get(SharedTrace, trace_id)

        if trace is None:
            return render_template("404.html"), 404

        if trace_id not in _PINNED_IDS and trace.expires_at < _utcnow():
            return render_template("expired.html"), 410

        view_count = (trace.view_count or 0) + 1
        trace.view_count = view_count
        # Copy what the template needs before commit expires the ORM object.
        payload = trace.payload
        trace_created_at = trace.created_at
        session.commit()

    run = payload["run"]
    raw_spans = payload.get("spans", [])

    run_start = _parse_dt(run.get("started_at"))
    run_end   = _parse_dt(run.get("ended_at")) or _utcnow()
    run_duration_ms = max(_ms(run_end - run_start), 1.0)

    llm_count = 0
    total_tokens = 0
    total_cost_usd = 0.0
    models_set = set()
    cost_rows = []

    span_data = []
    for sp in raw_spans:
        sp_start = _parse_dt(sp.get("started_at"))
        sp_end   = _parse_dt(sp.get("ended_at")) or _utcnow()
        sp_dur   = max(_ms(sp_end - sp_start), 0.0)
        offset   = max(_ms(sp_start - run_start), 0.0)

        start_pct = min(offset / run_duration_ms * 100, 99.0)
        width_pct = max(sp_dur / run_duration_ms * 100, 0.5)
        width_pct = min(width_pct, 100.0 - start_pct)

        meta = _coerce_json(sp.get("metadata") or sp.get("metadata_json"))

        span_data.append({
            "id": sp.get("id", ""),
            "name": sp.get("name", ""),
            "kind": sp.get("kind", "custom"),
            "status": sp.get("status", "ok"),
            "duration_ms": round(sp_dur, 1),
            "start_pct": round(start_pct, 3),
            "width_pct": round(width_pct, 3),
            "input": _coerce_json(sp.get("input") or sp.get("input_json")),
            "output": _coerce_json(sp.get("output") or sp.get("output_json")),
            "metadata": meta,
        })

        if sp.get("kind") == "llm":
            llm_count += 1
            prompt_tokens = 0
            completion_tokens = 0
            cost_usd = 0.0
            model = None
            if meta:
                model = meta.get("model")
                prompt_tokens = meta.get("prompt_tokens", 0) or 0
                completion_tokens = meta.get("completion_tokens", 0) or 0
                cost_usd = meta.get("cost_usd", 0.0) or 0.0
            total_tokens += prompt_tokens + completion_tokens
            total_cost_usd += cost_usd
            if model:
                models_set.add(model)
            cost_rows.append({
                "name": sp.get("name", ""),
                "model": model or "—",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": round(sp_dur, 1),
                "cost_usd": cost_usd,
            })

    cost_rows.sort(key=lambda r: r["cost_usd"], reverse=True)

    spans_by_id = {sp["id"]: sp for sp in span_data}

    if len(models_set) == 1:
        models_display = models_set.pop()
    elif len(models_set) > 1:
        models_display = f"{len(models_set)} models"
    else:
        models_display = None

    created_at_date = trace_created_at.strftime("%b %d, %Y")

    return render_template(
        "trace_viewer.html",
        run=run,
        spans=span_data,
        spans_json=json.dumps(spans_by_id),
        run_duration_ms=round(run_duration_ms),
        llm_count=llm_count,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        cost_rows=cost_rows,
        cost_rows_json=json.dumps(cost_rows),
        models_display=models_display,
        share_url=f"{_BASE_URL}/t/{trace_id}",
        shared_ago=_age_string(trace_created_at),
        created_at_date=created_at_date,
        view_count=view_count,
        embed=embed,
    )


@app.get("/t/<trace_id>")
def view_trace(trace_id):
    """Public viewer page."""
    return _render_trace(trace_id, embed=False)


@app.get("/t/<trace_id>/embed")
def view_trace_embed(trace_id):
    """Embeddable viewer — chrome-less version for iframes."""
    return _render_trace(trace_id, embed=True)


if __name__ == "__main__":
    _init_db()
    port = int(os.environ.get("PORT", 5051))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
