"""Client for the hosted share service. Mocked until Railway wiring session."""
import random
import re
import string

from sqlalchemy import select

from glasspipe.storage import Run, Span, get_session

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"(key|secret|password|token|auth)", re.IGNORECASE)
_VAL_RE = re.compile(r"^(sk-|Bearer |eyJ|AKIA|AIza)")


def redact(value, _key=None):
    """Recursively redact secrets from dicts/lists/strings.

    Triggers on key names matching common secret field names, or on string
    values that look like API keys or auth tokens.
    """
    if isinstance(value, dict):
        return {k: redact(v, _key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and value:
        if (_key and _KEY_RE.search(str(_key))) or _VAL_RE.match(value):
            return "[REDACTED]"
    return value


def _short_id(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def upload_run(run_id: str) -> str:
    """Package run + spans and return a shareable URL.

    Currently mocked — returns https://glasspipe.dev/t/<random-id> without
    any network call. Real POST to Railway replaces this in the infra session.
    """
    with get_session() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run {run_id!r} not found in local DB")
        spans = session.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.started_at)
        ).scalars().all()

    # Bundle payload — mirrors what the real API will receive
    _payload = {
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
                "input_json": sp.input_json,
                "output_json": sp.output_json,
                "metadata_json": sp.metadata_json,
            }
            for sp in spans
        ],
    }

    # TODO: replace with real POST to https://api.glasspipe.dev/share
    share_id = _short_id()
    return f"https://glasspipe.dev/t/{share_id}"
