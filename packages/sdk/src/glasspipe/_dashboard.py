"""GlassPipe local dashboard — Flask app."""
import json
import re as _re
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template
from markupsafe import Markup, escape
from sqlalchemy import func, select

from glasspipe.redact import detect, redact
from glasspipe.storage import Run, Span, get_session, init_db

_HERE = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(_HERE / "templates"),
    static_folder=str(_HERE / "static"),
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _ms(delta) -> float:
    return delta.total_seconds() * 1000


# ---------------------------------------------------------------------------
# Jinja filters
# ---------------------------------------------------------------------------

@app.template_filter("redacted_json")
def redacted_json_filter(obj) -> Markup:
    """Render a (post-redact) Python object as indented JSON with [REDACTED]
    values highlighted in orange. Safe for use inside <pre> tags."""
    if obj is None:
        return Markup('<span class="dimmed">null</span>')
    raw = json.dumps(obj, indent=2)
    safe = str(escape(raw))
    # Match [REDACTED] (old format) and [REDACTED:type] (new format)
    safe = _re.sub(
        r'&quot;(\[REDACTED(?::[a-z_]+)?\])&quot;',
        lambda m: f'<span class="redacted">&quot;{m.group(1)}&quot;</span>',
        safe,
    )
    return Markup(safe)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    init_db()
    with get_session() as session:
        runs = session.execute(
            select(Run).order_by(Run.started_at.desc()).limit(20)
        ).scalars().all()

        run_ids = [r.id for r in runs]
        counts: dict[str, int] = {}
        if run_ids:
            rows = session.execute(
                select(Span.run_id, func.count().label("n"))
                .where(Span.run_id.in_(run_ids))
                .group_by(Span.run_id)
            ).all()
            counts = {row.run_id: row.n for row in rows}

        now = _utcnow()
        run_data = []
        for run in runs:
            end = run.ended_at or now
            run_data.append({
                "id": run.id,
                "name": run.name,
                "started_at": run.started_at,
                "duration_ms": round(_ms(end - run.started_at)),
                "span_count": counts.get(run.id, 0),
                "status": run.status,
            })

    return render_template("index.html", runs=run_data)


@app.route("/run/<run_id>")
def run_detail(run_id):
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            abort(404)

        spans = session.execute(
            select(Span)
            .where(Span.run_id == run_id)
            .order_by(Span.started_at)
        ).scalars().all()

        now = _utcnow()
        run_end = run.ended_at or now
        run_duration_ms = max(_ms(run_end - run.started_at), 1.0)

        span_data = []
        for sp in spans:
            sp_end = sp.ended_at or now
            sp_dur = max(_ms(sp_end - sp.started_at), 0.0)
            offset = max(_ms(sp.started_at - run.started_at), 0.0)

            start_pct = min(offset / run_duration_ms * 100, 99.0)
            width_pct = max(sp_dur / run_duration_ms * 100, 0.5)
            width_pct = min(width_pct, 100.0 - start_pct)

            span_data.append({
                "id": sp.id,
                "name": sp.name,
                "kind": sp.kind,
                "status": sp.status,
                "duration_ms": round(sp_dur, 1),
                "start_pct": round(start_pct, 3),
                "width_pct": round(width_pct, 3),
            })

    return render_template(
        "run_detail.html",
        run=run,
        spans=span_data,
        run_duration_ms=round(run_duration_ms),
    )


@app.route("/span/<span_id>")
def span_detail(span_id):
    with get_session() as session:
        sp = session.get(Span, span_id)
        if sp is None:
            abort(404)

        def _safe_parse(s):
            if not s:
                return None
            try:
                return json.loads(s)
            except Exception:
                return s  # return raw string rather than 500

        input_data = _safe_parse(sp.input_json)
        output_data = _safe_parse(sp.output_json)
        metadata = _safe_parse(sp.metadata_json)

    return render_template(
        "span_detail.html",
        span=sp,
        input_data=input_data,
        output_data=output_data,
        metadata=metadata,
    )


@app.get("/share/preview/<run_id>")
def share_preview(run_id):
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            abort(404)

        spans = session.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.started_at)
        ).scalars().all()

        now = _utcnow()
        run_end = run.ended_at or now
        run_duration_ms = round(_ms(run_end - run.started_at))

        total_redacted = 0
        span_previews = []
        for sp in spans:
            sp_end = sp.ended_at or now
            raw_input  = json.loads(sp.input_json)  if sp.input_json  else None
            raw_output = json.loads(sp.output_json) if sp.output_json else None

            # Count secrets before redacting so we can report the number
            for raw in (raw_input, raw_output):
                if raw is not None:
                    total_redacted += len(detect(json.dumps(raw)))

            span_previews.append({
                "name": sp.name,
                "kind": sp.kind,
                "status": sp.status,
                "duration_ms": round(_ms(sp_end - sp.started_at), 1),
                "input":  redact(raw_input),
                "output": redact(raw_output),
            })

    return render_template(
        "share_preview.html",
        run=run,
        run_duration_ms=run_duration_ms,
        span_count=len(span_previews),
        spans=span_previews,
        total_redacted=total_redacted,
    )


@app.get("/share/cancel")
def share_cancel():
    return ""


@app.post("/share/confirm/<run_id>")
def share_confirm(run_id):
    from glasspipe.share import upload_run

    url = upload_run(run_id)
    return render_template("share_success.html", url=url)
