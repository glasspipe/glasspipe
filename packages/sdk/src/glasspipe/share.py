"""Client for the hosted share service."""
import json
import os
import random
import string
import sys

import httpx
from sqlalchemy import select

from glasspipe.redact import redact_trace
from glasspipe.storage import Run, Span, get_session


def _short_id(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def _build_payload(run_id: str) -> dict:
    """Read run + spans from local DB and assemble the API payload."""
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run {run_id!r} not found in local DB")
        spans = session.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.started_at)
        ).scalars().all()

    def _parse(s):
        if s is None:
            return None
        try:
            return json.loads(s)
        except Exception:
            return s

    return {
        "run": {
            "id": run.id,
            "name": run.name,
            "started_at": run.started_at.isoformat(),
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "status": run.status,
            "error_message": run.error_message,
        },
        "spans": [
            {
                "id": sp.id,
                "run_id": sp.run_id,
                "parent_span_id": sp.parent_span_id,
                "kind": sp.kind,
                "name": sp.name,
                "started_at": sp.started_at.isoformat(),
                "ended_at": sp.ended_at.isoformat() if sp.ended_at else None,
                "status": sp.status,
                "input": _parse(sp.input_json),
                "output": _parse(sp.output_json),
                "metadata": _parse(sp.metadata_json),
            }
            for sp in spans
        ],
    }


def upload_run(run_id: str) -> str:
    """Package run + spans, redact secrets, and return a shareable URL.

    Behaviour:
    - GLASSPIPE_SHARE_API=mock  → local mock URL, no network call
    - GLASSPIPE_SHARE_API=<url> → POST to that URL
    - Any connection error      → silent fallback to mock
    """
    api_url = os.environ.get(
        "GLASSPIPE_SHARE_API",
        "https://glasspipe-app-production.up.railway.app/v1/share",
    )

    payload = _build_payload(run_id)
    payload = redact_trace(payload)  # sanitize before upload

    if api_url == "mock":
        return f"https://glasspipe.dev/t/{_short_id()}"

    try:
        resp = httpx.post(api_url, json=payload, timeout=10.0)
        resp.raise_for_status()
        return resp.json()["url"]
    except Exception as exc:
        print(
            f"glasspipe warning: share API unreachable ({type(exc).__name__}), "
            "using local mock URL",
            file=sys.stderr,
        )
        return f"https://glasspipe.dev/t/{_short_id()}"
