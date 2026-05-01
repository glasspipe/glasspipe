"""GlassPipe local dashboard — Flask app."""
import json
import re as _re
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template, request
from markupsafe import Markup, escape
from sqlalchemy import func, select

from glasspipe._diff import diff_runs
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

@app.template_filter("format_cost")
def format_cost_filter(value):
    if not value or value == 0:
        return "$0"
    if value >= 1.0:
        s = f"{value:.6f}".rstrip("0")
        if s.endswith("."):
            s += "00"
        elif len(s.split(".", 1)[1]) < 2:
            s += "0" * (2 - len(s.split(".", 1)[1]))
        return "$" + s
    cents = value * 100
    if cents < 0.001:
        return "< 0.001¢"
    s = f"{cents:.6f}".rstrip("0").rstrip(".")
    return s + "¢"


def _display_name(name: str, kind: str, metadata: dict | None = None) -> str:
    if kind == "llm":
        model = None
        if metadata:
            model = metadata.get("model")
        if "openai" in name:
            provider = "OpenAI"
        elif "anthropic" in name:
            provider = "Anthropic"
        else:
            provider = None
        parts = ["LLM Call"]
        if provider:
            parts.append(provider)
        elif model:
            parts.append(model)
        return " · ".join(parts)
    if kind == "tool":
        return name.replace("_", " ").title()
    return name


@app.template_filter("display_name")
def display_name_filter(name, kind=None, metadata=None):
    if kind is None:
        return name
    return _display_name(name, kind, metadata)


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


def _safe_parse_meta(s):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


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

        span_name_by_id = {sp.id: sp.name for sp in spans}

        llm_count = 0
        total_tokens = 0
        total_cost_usd = 0.0
        cost_rows = []

        span_data = []
        for sp in spans:
            sp_end = sp.ended_at or now
            sp_dur = max(_ms(sp_end - sp.started_at), 0.0)
            offset = max(_ms(sp.started_at - run.started_at), 0.0)

            start_pct = min(offset / run_duration_ms * 100, 99.0)
            width_pct = max(sp_dur / run_duration_ms * 100, 0.5)
            width_pct = min(width_pct, 100.0 - start_pct)

            meta = _safe_parse_meta(sp.metadata_json)

            span_data.append({
                "id": sp.id,
                "name": sp.name,
                "display_name": _display_name(sp.name, sp.kind, meta),
                "kind": sp.kind,
                "status": sp.status,
                "duration_ms": round(sp_dur, 1),
                "start_pct": round(start_pct, 3),
                "width_pct": round(width_pct, 3),
                "metadata": meta,
            })

            if sp.kind == "llm":
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
                parent_name = span_name_by_id.get(sp.parent_span_id, "")
                cost_rows.append({
                    "name": sp.name,
                    "display_name": _display_name(sp.name, sp.kind, meta),
                    "parent_name": parent_name,
                    "model": model or "—",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "duration_ms": round(sp_dur, 1),
                    "cost_usd": cost_usd,
                })

        cost_rows.sort(key=lambda r: r["cost_usd"], reverse=True)

        span_count = len(span_data)

    return render_template(
        "run_detail.html",
        run=run,
        spans=span_data,
        run_duration_ms=round(run_duration_ms),
        llm_count=llm_count,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        span_count=span_count,
        cost_rows=cost_rows,
    )


@app.route("/compare")
def compare():
    a_id = request.args.get("a")
    b_id = request.args.get("b")

    if not a_id or not b_id:
        return render_template("compare.html", error="Pick two runs from the run list to compare."), 400

    if a_id == b_id:
        return render_template("compare.html", error="Pick two different runs to compare."), 400

    with get_session() as session:
        run_a = session.get(Run, a_id)
        run_b = session.get(Run, b_id)

        if run_a is None or run_b is None:
            missing = a_id if run_a is None else b_id
            return render_template("compare.html", error=f"Run {missing} not found."), 404

        spans_a = session.execute(
            select(Span).where(Span.run_id == a_id).order_by(Span.started_at)
        ).scalars().all()

        spans_b = session.execute(
            select(Span).where(Span.run_id == b_id).order_by(Span.started_at)
        ).scalars().all()

        now = _utcnow()
        dur_a = max(_ms((run_a.ended_at or now) - run_a.started_at), 1.0)
        dur_b = max(_ms((run_b.ended_at or now) - run_b.started_at), 1.0)

        result = diff_runs(spans_a, spans_b, dur_a, dur_b)

        max_dur = max(dur_a, dur_b)

        def _waterfall_data(diff_spans, run, run_dur):
            now_l = _utcnow()
            run_start = run.started_at
            data = []
            for ds in diff_spans:
                sp = ds.span
                sp_end = sp.ended_at or now_l
                sp_dur = max(_ms(sp_end - sp.started_at), 0.0)
                offset = max(_ms(sp.started_at - run_start), 0.0)

                start_pct = min(offset / max_dur * 100, 99.0)
                width_pct = max(sp_dur / max_dur * 100, 0.5)
                width_pct = min(width_pct, 100.0 - start_pct)

                data.append({
                    "id": sp.id,
                    "name": sp.name,
                    "kind": sp.kind,
                    "status": sp.status,
                    "duration_ms": round(sp_dur, 1),
                    "start_pct": round(start_pct, 3),
                    "width_pct": round(width_pct, 3),
                    "diff_status": ds.diff_status,
                    "depth": ds.depth,
                })
            return data

        waterfall_a = _waterfall_data(result.spans_a, run_a, dur_a)
        waterfall_b = _waterfall_data(result.spans_b, run_b, dur_b)

    dur_delta_pct = None
    if dur_a > 0:
        dur_delta_pct = round((dur_b - dur_a) / dur_a * 100, 1)

    return render_template(
        "compare.html",
        run_a=run_a,
        run_b=run_b,
        waterfall_a=waterfall_a,
        waterfall_b=waterfall_b,
        result=result,
        max_duration_ms=round(max_dur),
        dur_delta_pct=dur_delta_pct,
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
                return s

        input_data = _safe_parse(sp.input_json)
        output_data = _safe_parse(sp.output_json)
        metadata = _safe_parse(sp.metadata_json)

    def _fmt_dur(ms):
        if ms < 1000:
            return f"{round(ms)}ms"
        return f"{round(ms / 1000, 1)}s"

    duration_ms = 0.0
    if sp.ended_at and sp.started_at:
        duration_ms = (sp.ended_at - sp.started_at).total_seconds() * 1000

    insight = None
    if sp.status == "error":
        insight = f"This step failed after {_fmt_dur(duration_ms)}. See the output below for the error details."
    elif sp.kind == "llm" and metadata:
        model = metadata.get("model", "LLM")
        prompt_tokens = metadata.get("prompt_tokens") or 0
        completion_tokens = metadata.get("completion_tokens") or 0
        cost_usd = metadata.get("cost_usd") or 0
        dur_str = _fmt_dur(duration_ms)

        if duration_ms > 3000 and prompt_tokens > 100:
            insight = f"{model} took {dur_str} — slower than usual. Large prompt ({prompt_tokens} tokens) may be the cause."
        elif prompt_tokens > 0 or completion_tokens > 0:
            cost_str = format_cost_filter(cost_usd)
            insight = f"{model} took {dur_str} to process {prompt_tokens} tokens and generate {completion_tokens} tokens, costing {cost_str}."
        else:
            insight = f"{model} took {dur_str}."
    elif sp.kind == "llm":
        insight = f"LLM call took {_fmt_dur(duration_ms)}."
    elif sp.kind in ("tool", "custom"):
        dname = _display_name(sp.name, sp.kind, metadata)
        insight = f"{dname} completed in {_fmt_dur(duration_ms)}."
    elif sp.kind == "agent":
        dname = _display_name(sp.name, sp.kind, metadata)
        insight = f"{dname} ran for {_fmt_dur(duration_ms)}."
    else:
        dname = _display_name(sp.name, sp.kind, metadata)
        insight = f"{dname} completed in {_fmt_dur(duration_ms)}."

    return render_template(
        "span_detail.html",
        span=sp,
        input_data=input_data,
        output_data=output_data,
        metadata=metadata,
        insight=insight,
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
