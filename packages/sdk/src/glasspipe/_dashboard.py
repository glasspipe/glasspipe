"""GlassPipe local dashboard — Flask app."""
import hashlib
import json
import os
import re as _re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


from flask import Flask, abort, jsonify, render_template, request
from markupsafe import Markup, escape
from sqlalchemy import func, select

from glasspipe._diff import diff_runs
from glasspipe.instruments.openai_patch import _PRICING as _OPENAI_PRICING, _normalize_model as _norm_openai
from glasspipe.redact import detect, redact
from glasspipe.storage import Run, Span, get_session, init_db

_HERE = Path(__file__).parent

app = Flask(
    __name__,
    template_folder=str(_HERE / "templates"),
    static_folder=str(_HERE / "static"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_sub(a, b):
    if a.tzinfo is not None and b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    elif a.tzinfo is None and b.tzinfo is not None:
        a = a.replace(tzinfo=timezone.utc)
    return a - b


def _estimate_cost(model, prompt_tokens, completion_tokens):
    if not model:
        return 0.0
    inp, out = _OPENAI_PRICING.get(
        model, _OPENAI_PRICING.get(_norm_openai(model), (0.0, 0.0))
    )
    if inp == 0.0 and out == 0.0:
        return 0.0
    return (prompt_tokens * inp + completion_tokens * out) / 1_000_000


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


@app.template_filter("commaify")
def commaify_filter(value):
    return f"{int(value):,}"


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
        r'(?:&quot;|&#34;)(\[REDACTED(?::[a-z_]+)?\])(?:&quot;|&#34;)',
        lambda m: f'<span class="redacted">{m.group(1)}</span>',
        safe,
    )
    return Markup(safe)


# ---------------------------------------------------------------------------
# DNA + Fingerprint helpers
# ---------------------------------------------------------------------------

_DNA_KIND_MAP = {
    "llm": "kind-llm",
    "tool": "kind-tool",
    "agent": "kind-agent",
    "custom": "kind-custom",
}
_DNA_MAX_BLOCKS = 20


def build_dna(spans):
    blocks = []
    for s in spans[:_DNA_MAX_BLOCKS - 1]:
        blocks.append({"kind": _DNA_KIND_MAP.get(s["kind"], "kind-other")})
    remaining = len(spans) - (_DNA_MAX_BLOCKS - 1)
    if remaining > 0:
        blocks.append({"kind": "overflow", "count": remaining + 1})
    return blocks


def build_fingerprint(run_name, spans):
    sig = run_name + "|" + ",".join(f"{s['kind']}:{s['name']}" for s in spans)
    digest = hashlib.md5(sig.encode()).hexdigest()
    bits = bin(int(digest[:7], 16))[2:].zfill(25)
    grid = [b == "1" for b in bits[:25]]
    return grid, digest[:6]


# ---------------------------------------------------------------------------
# Context window limits
# ---------------------------------------------------------------------------

CONTEXT_LIMITS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    "gpt-4.1-nano": 128_000,
    "o3-mini": 128_000,
    "o4-mini": 128_000,
    "claude-opus-4": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-haiku-4": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-haiku-4-5": 200_000,
}


def get_context_limit(model_name: str) -> int | None:
    if not model_name:
        return None
    key = model_name.lower()
    key = key.split("-202")[0]
    return CONTEXT_LIMITS.get(key)


# ---------------------------------------------------------------------------
# Oh-shit detector
# ---------------------------------------------------------------------------

def check_anomalies(run_id: str) -> list[dict]:
    try:
        now = _utcnow()
        with get_session() as session:
            run = session.get(Run, run_id)
            if run is None or run.status != "running":
                return []

            spans = session.execute(
                select(Span)
                .where(Span.run_id == run_id)
                .order_by(Span.started_at)
            ).scalars().all()

            anomalies = []

            # CHECK 1 — Repeated tool call
            tool_names = [sp.name for sp in spans if sp.kind == "tool" and sp.status == "ok"]
            if tool_names:
                best_name = None
                best_count = 0
                cur_name = tool_names[0]
                cur_count = 1
                for n in tool_names[1:]:
                    if n == cur_name:
                        cur_count += 1
                    else:
                        if cur_count > best_count:
                            best_count = cur_count
                            best_name = cur_name
                        cur_name = n
                        cur_count = 1
                if cur_count > best_count:
                    best_count = cur_count
                    best_name = cur_name
                if best_count >= 5:
                    anomalies.append({
                        "code": "LOOP_SUSPECTED",
                        "message": f"'{best_name}' called {best_count}\u00d7 in a row \u2014 possible loop",
                        "severity": "danger",
                    })

            # CHECK 2 — Cost spike
            total_cost = 0.0
            for sp in spans:
                if sp.metadata_json and sp.status == "ok":
                    meta = _safe_parse_meta(sp.metadata_json)
                    if meta:
                        cost = meta.get("cost_usd")
                        if cost is not None:
                            try:
                                total_cost += float(cost)
                            except (TypeError, ValueError):
                                pass
            threshold = float(os.environ.get("GLASSPIPE_COST_ALERT_USD", "0.50"))
            if total_cost > threshold:
                anomalies.append({
                    "code": "COST_SPIKE",
                    "message": f"run cost ${total_cost:.3f} \u2014 threshold ${threshold:.2f}",
                    "severity": "warn",
                })

            # CHECK 3 — Step count spike
            completed_count = sum(1 for sp in spans if sp.status == "ok")
            if completed_count > 10:
                avg_rows = session.execute(
                    select(func.count().label("n"))
                    .where(Run.name == run.name)
                    .where(Run.status == "ok")
                    .order_by(Run.started_at.desc())
                    .limit(20)
                ).first()
                if avg_rows and avg_rows.n > 0:
                    span_counts = []
                    past_runs = session.execute(
                        select(Run.id)
                        .where(Run.name == run.name)
                        .where(Run.status == "ok")
                        .where(Run.id != run_id)
                        .order_by(Run.started_at.desc())
                        .limit(20)
                    ).scalars().all()
                    if past_runs:
                        past_ids = list(past_runs)
                        count_rows = session.execute(
                            select(Span.run_id, func.count().label("n"))
                            .where(Span.run_id.in_(past_ids))
                            .where(Span.status == "ok")
                            .group_by(Span.run_id)
                        ).all()
                        span_counts = [r.n for r in count_rows]
                    if span_counts:
                        avg = sum(span_counts) / len(span_counts)
                        if completed_count > avg * 2.5 and completed_count > 10:
                            anomalies.append({
                                "code": "STEP_COUNT",
                                "message": f"{completed_count} steps \u2014 {avg:.0f} is normal for this agent",
                                "severity": "warn",
                            })

            # CHECK 4 — Long running
            if run.started_at:
                elapsed = _safe_sub(now, run.started_at)
                minutes = elapsed.total_seconds() / 60.0
                if minutes > 5:
                    anomalies.append({
                        "code": "LONG_RUNNING",
                        "message": f"running for {minutes:.0f} min \u2014 agents usually finish faster",
                        "severity": "warn",
                    })

            return anomalies
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _build_run_data(runs, now=None):
    if now is None:
        now = _utcnow()
    local_now = datetime.now()
    today = local_now.date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    run_ids = [r.id for r in runs]
    counts: dict[str, int] = {}
    if run_ids:
        with get_session() as session:
            rows = session.execute(
                select(Span.run_id, func.count().label("n"))
                .where(Span.run_id.in_(run_ids))
                .group_by(Span.run_id)
            ).all()
            counts = {row.run_id: row.n for row in rows}
    run_data = []
    for run in runs:
        start = run.started_at
        end = run.ended_at or now
        if start.tzinfo is not None:
            run_date = start.astimezone().date()
        else:
            run_date = start.date()
        if run_date == today:
            date_label = "today"
            date_sort = 0
        elif run_date == yesterday:
            date_label = "yesterday"
            date_sort = 1
        elif run_date >= week_ago:
            date_label = "this week"
            date_sort = 2
        else:
            date_label = run_date.strftime("%b %d, %Y")
            date_sort = 3
        run_data.append({
            "id": run.id,
            "name": run.name,
            "agent_version": run.agent_version,
            "started_at": run.started_at,
            "duration_ms": round(_ms(_safe_sub(end, start))),
            "span_count": counts.get(run.id, 0),
            "status": run.status,
            "date_label": date_label,
            "date_sort": date_sort,
        })
    return run_data


@app.route("/")
def index():
    init_db()
    version_filter = request.args.get("version")
    with get_session() as session:
        query = select(Run).order_by(Run.started_at.desc()).limit(20)
        if version_filter:
            query = query.where(Run.agent_version == version_filter)
        runs = session.execute(query).scalars().all()

        run_ids = [r.id for r in runs]
        spans_rows = []
        if run_ids:
            spans_rows = session.execute(
                select(Span.run_id, Span.kind, Span.name, Span.started_at)
                .where(Span.run_id.in_(run_ids))
                .order_by(Span.started_at)
            ).all()

    spans_by_run = defaultdict(list)
    for row in spans_rows:
        spans_by_run[row.run_id].append({"kind": row.kind, "name": row.name})

    run_data = _build_run_data(runs)
    for rd in run_data:
        run_spans = spans_by_run.get(rd["id"], [])
        rd["dna"] = build_dna(run_spans)
        rd["fingerprint"], rd["fp_hash"] = build_fingerprint(rd["name"], run_spans)

    versions = sorted({r.agent_version for r in runs if r.agent_version})
    return render_template("index.html", runs=run_data, versions=versions, current_version=version_filter)


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
        run_duration_ms = max(_ms(_safe_sub(run_end, run.started_at)), 1.0)

        span_name_by_id = {sp.id: sp.name for sp in spans}

        fp_spans = [{"kind": sp.kind, "name": sp.name} for sp in spans]
        fingerprint, fp_hash = build_fingerprint(run.name, fp_spans)

        llm_count = 0
        total_tokens = 0
        total_cost_usd = 0.0
        cost_rows = []

        span_data = []
        for sp in spans:
            sp_end = sp.ended_at or now
            sp_dur = max(_ms(_safe_sub(sp_end, sp.started_at)), 0.0)
            offset = max(_ms(_safe_sub(sp.started_at, run.started_at)), 0.0)

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
                    if cost_usd == 0.0 and model and (prompt_tokens or completion_tokens):
                        cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)
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
        fingerprint=fingerprint,
        fp_hash=fp_hash,
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
        dur_a = max(_ms(_safe_sub(run_a.ended_at or now, run_a.started_at)), 1.0)
        dur_b = max(_ms(_safe_sub(run_b.ended_at or now, run_b.started_at)), 1.0)

        result = diff_runs(spans_a, spans_b, dur_a, dur_b)

        max_dur = max(dur_a, dur_b)

        def _waterfall_data(diff_spans, run, run_dur):
            now_l = _utcnow()
            run_start = run.started_at
            data = []
            for ds in diff_spans:
                sp = ds.span
                sp_end = sp.ended_at or now_l
                sp_dur = max(_ms(_safe_sub(sp_end, sp.started_at)), 0.0)
                offset = max(_ms(_safe_sub(sp.started_at, run_start)), 0.0)

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
        if cost_usd == 0 and (prompt_tokens or completion_tokens):
            cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)
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

    context_gauge = None
    if sp.kind == "llm" and metadata:
        model = metadata.get("model")
        prompt_tokens = metadata.get("prompt_tokens") or 0
        if model and prompt_tokens:
            limit = get_context_limit(model)
            if limit:
                pct = min(prompt_tokens / limit * 100, 100.0)
                level = "danger" if pct > 85 else ("warn" if pct > 60 else "ok")
                context_gauge = {
                    "pct": round(pct, 1),
                    "tokens": prompt_tokens,
                    "limit": limit,
                    "level": level,
                }
            else:
                context_gauge = {"unknown": model}

    return render_template(
        "span_detail.html",
        span=sp,
        input_data=input_data,
        output_data=output_data,
        metadata=metadata,
        insight=insight,
        context_gauge=context_gauge,
    )


@app.get("/anomalies/<run_id>")
def anomalies_route(run_id):
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "running":
            return jsonify([])
    detected = check_anomalies(run_id)
    if not detected:
        return jsonify([])
    return jsonify(detected)


@app.get("/anomalies-banner/<run_id>")
def anomalies_banner_route(run_id):
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "running":
            return ""
    detected = check_anomalies(run_id)
    if not detected:
        return ""
    return render_template("_anomaly_banner.html", anomalies=detected)


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
        run_duration_ms = round(_ms(_safe_sub(run_end, run.started_at)))

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
                "duration_ms": round(_ms(_safe_sub(sp_end, sp.started_at)), 1),
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
    from glasspipe.share import upload_run, ShareError

    try:
        url = upload_run(run_id)
        return render_template("share_success.html", url=url)
    except ShareError as exc:
        return render_template("share_error.html", error=str(exc))


@app.delete("/runs/<run_id>")
def delete_run(run_id):
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            abort(404)
        session.query(Span).filter_by(run_id=run_id).delete()
        session.delete(run)
        session.commit()

        remaining = session.execute(
            select(Run).order_by(Run.started_at.desc()).limit(20)
        ).scalars().all()
        if not remaining:
            return render_template("index.html", runs=[])
        return render_template("index.html", runs=_build_run_data(remaining))


@app.post("/runs/clear")
def clear_runs():
    with get_session() as session:
        session.query(Span).delete()
        session.query(Run).delete()
        session.commit()
    return render_template("index.html", runs=[])
