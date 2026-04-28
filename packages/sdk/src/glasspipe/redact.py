"""Redaction utilities — strip secrets and PII from trace data before sharing."""
import json
import os
import re

PATTERNS: dict[str, str] = {
    "openai_key":     r"sk-[a-zA-Z0-9]{20,}",
    "anthropic_key":  r"sk-ant-[a-zA-Z0-9\-_]{20,}",
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret_key": r"[a-zA-Z0-9/+=]{40}",
    "github_token":   r"gh[pousr]_[A-Za-z0-9]{36,}",
    "jwt":            r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*",
    "email":          r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "credit_card":    r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "phone_us":       r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
    "url_with_query": r"https?://[^\s]+\?[^\s]+",
}


def _load_env_patterns() -> dict[str, str]:
    raw = os.environ.get("GLASSPIPE_REDACT_PATTERNS")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _merged_patterns(custom_patterns: dict | None) -> dict[str, str]:
    return {**PATTERNS, **(custom_patterns or {}), **_load_env_patterns()}


def detect(text: str) -> list[dict]:
    """Scan a string for sensitive patterns.

    Returns a list of matches, each as:
        {"type": str, "match": str, "start": int, "end": int}
    Sorted by start position.
    """
    results = []
    for name, pattern in _merged_patterns(None).items():
        for m in re.finditer(pattern, text):
            results.append({
                "type": name,
                "match": m.group(),
                "start": m.start(),
                "end": m.end(),
            })
    results.sort(key=lambda x: x["start"])
    return results


def redact(value, custom_patterns: dict | None = None):
    """Recursively walk dicts/lists, replacing sensitive strings with [REDACTED:type].

    custom_patterns: optional {name: regex} dict merged with PATTERNS.
    GLASSPIPE_REDACT_PATTERNS env var (JSON dict) is also merged.
    """
    patterns = _merged_patterns(custom_patterns)

    def _redact_str(s: str) -> str:
        for name, pattern in patterns.items():
            s = re.sub(pattern, f"[REDACTED:{name}]", s)
        return s

    def _walk(v):
        if isinstance(v, dict):
            return {k: _walk(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_walk(item) for item in v]
        if isinstance(v, str):
            return _redact_str(v)
        return v

    return _walk(value)


def redact_trace(trace: dict, custom_patterns: dict | None = None) -> dict:
    """Redact all span input/output in a full trace payload {run, spans}.

    Returns a new dict; the original is not mutated.
    """
    result = {**trace}
    result["spans"] = [
        {
            **sp,
            "input":  redact(sp["input"],  custom_patterns) if sp.get("input")  is not None else None,
            "output": redact(sp["output"], custom_patterns) if sp.get("output") is not None else None,
        }
        for sp in trace.get("spans", [])
    ]
    return result
