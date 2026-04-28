"""GlassPipe local dashboard — Flask app (3 routes)."""
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template
from sqlalchemy import func, select

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

        input_data = json.loads(sp.input_json) if sp.input_json else None
        output_data = json.loads(sp.output_json) if sp.output_json else None
        metadata = json.loads(sp.metadata_json) if sp.metadata_json else None

    return render_template(
        "span_detail.html",
        span=sp,
        input_data=input_data,
        output_data=output_data,
        metadata=metadata,
    )
