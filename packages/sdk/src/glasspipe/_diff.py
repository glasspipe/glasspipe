"""Pure diffing logic for comparing two GlassPipe runs.

No Flask, no templates, no DB session — just data in, data out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from glasspipe.storage import Span


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DiffSpan:
    span: Span
    match_key: tuple[str, str, int, int]
    diff_status: str  # "only_in_a" | "only_in_b" | "in_both"
    partner_id: str | None = None
    depth: int = 0


@dataclass
class CompareResult:
    spans_a: list[DiffSpan]
    spans_b: list[DiffSpan]
    only_in_a: int = 0
    only_in_b: int = 0
    in_both: int = 0
    duration_a_ms: float = 0.0
    duration_b_ms: float = 0.0
    cost_a_usd: float | None = None
    cost_b_usd: float | None = None
    tokens_a: int | None = None
    tokens_b: int | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_children_map(spans: list[Span]) -> dict[str | None, list[Span]]:
    """Return {parent_span_id: [child spans]} ordered by started_at.

    Root spans have parent_span_id = None.
    """
    children: dict[str | None, list[Span]] = {}
    for sp in spans:
        pid = sp.parent_span_id
        children.setdefault(pid, []).append(sp)
    for v in children.values():
        v.sort(key=lambda s: s.started_at)
    return children


def _compute_depths(spans: list[Span]) -> dict[str, int]:
    """Return {span_id: depth} where root spans are depth 0."""
    by_id = {sp.id: sp for sp in spans}
    depths: dict[str, int] = {}

    def _depth(sid: str) -> int:
        if sid in depths:
            return depths[sid]
        sp = by_id[sid]
        if sp.parent_span_id is None or sp.parent_span_id not in by_id:
            d = 0
        else:
            d = _depth(sp.parent_span_id) + 1
        depths[sid] = d
        return d

    for sp in spans:
        _depth(sp.id)
    return depths


def _compute_match_keys(spans: list[Span]) -> dict[str, tuple[str, str, int, int]]:
    """Return {span_id: (name, kind, depth, sibling_index)}.

    sibling_index is the 0-based index among siblings that share the same
    (name, kind) under the same parent. This disambiguates multiple spans
    with identical name+kind (e.g. two "openai.chat" LLM calls).
    """
    children = _build_children_map(spans)
    depths = _compute_depths(spans)
    keys: dict[str, tuple[str, str, int, int]] = {}

    def _walk(parent_id: str | None) -> None:
        kids = children.get(parent_id, [])
        name_kind_count: dict[tuple[str, str], int] = {}
        for sp in kids:
            nk = (sp.name, sp.kind)
            idx = name_kind_count.get(nk, 0)
            name_kind_count[nk] = idx + 1
            keys[sp.id] = (sp.name, sp.kind, depths[sp.id], idx)
            _walk(sp.id)

    _walk(None)
    return keys


def _sum_llm_stats(spans: list[Span]) -> tuple[float | None, int | None]:
    """Sum cost_usd and (prompt + completion) tokens from LLM spans."""
    total_cost = 0.0
    total_tokens = 0
    found = False
    for sp in spans:
        if sp.kind != "llm" or not sp.metadata_json:
            continue
        try:
            meta = json.loads(sp.metadata_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if meta.get("cost_usd") is not None:
            total_cost += float(meta["cost_usd"])
            found = True
        pt = meta.get("prompt_tokens")
        ct = meta.get("completion_tokens")
        if pt is not None and ct is not None:
            total_tokens += int(pt) + int(ct)
            found = True
    if not found:
        return None, None
    return (total_cost if total_cost > 0 else 0.0) or 0.0, total_tokens or 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff_runs(
    spans_a: list[Span],
    spans_b: list[Span],
    run_a_duration_ms: float,
    run_b_duration_ms: float,
) -> CompareResult:
    """Compare spans from two runs and produce a diff result.

    Matching heuristic: spans are matched by (name, kind, depth,
    sibling_index_among_same_name_kind_siblings).  This is deterministic,
    handles common cases (same agent run twice), and degrades gracefully
    when structures diverge.
    """
    keys_a = _compute_match_keys(spans_a)
    keys_b = _compute_match_keys(spans_b)
    depths_a = _compute_depths(spans_a)
    depths_b = _compute_depths(spans_b)

    key_to_id_b: dict[tuple, str] = {}
    for sid, key in keys_b.items():
        key_to_id_b[key] = sid

    diff_a: list[DiffSpan] = []
    diff_b: list[DiffSpan] = []
    only_in_a = 0
    only_in_b = 0
    in_both = 0
    matched_b_ids: set[str] = set()

    for sp in spans_a:
        key = keys_a[sp.id]
        partner = key_to_id_b.get(key)
        if partner is not None:
            diff_a.append(DiffSpan(
                span=sp, match_key=key, diff_status="in_both",
                partner_id=partner, depth=depths_a[sp.id],
            ))
            matched_b_ids.add(partner)
            in_both += 1
        else:
            diff_a.append(DiffSpan(
                span=sp, match_key=key, diff_status="only_in_a",
                depth=depths_a[sp.id],
            ))
            only_in_a += 1

    for sp in spans_b:
        key = keys_b[sp.id]
        if sp.id in matched_b_ids:
            partner = None
            for sa in diff_a:
                if sa.partner_id == sp.id:
                    partner = sa.span.id
                    break
            diff_b.append(DiffSpan(
                span=sp, match_key=key, diff_status="in_both",
                partner_id=partner, depth=depths_b[sp.id],
            ))
        else:
            diff_b.append(DiffSpan(
                span=sp, match_key=key, diff_status="only_in_b",
                depth=depths_b[sp.id],
            ))
            only_in_b += 1

    cost_a, tokens_a = _sum_llm_stats(spans_a)
    cost_b, tokens_b = _sum_llm_stats(spans_b)

    return CompareResult(
        spans_a=diff_a,
        spans_b=diff_b,
        only_in_a=only_in_a,
        only_in_b=only_in_b,
        in_both=in_both,
        duration_a_ms=run_a_duration_ms,
        duration_b_ms=run_b_duration_ms,
        cost_a_usd=cost_a,
        cost_b_usd=cost_b,
        tokens_a=tokens_a,
        tokens_b=tokens_b,
    )
