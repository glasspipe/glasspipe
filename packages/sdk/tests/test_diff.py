"""Tests for glasspipe._diff — the pure diffing logic for comparing runs."""

from datetime import datetime, timezone

import pytest

from glasspipe._diff import DiffSpan, CompareResult, diff_runs
from glasspipe.storage import Span

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers — construct Span objects in-memory (no DB needed)
# ---------------------------------------------------------------------------

def _span(
    sid: str,
    run_id: str = "run_a",
    name: str = "span",
    kind: str = "custom",
    parent_span_id: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    status: str = "ok",
    metadata_json: str | None = None,
) -> Span:
    if started_at is None:
        started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    if ended_at is None:
        ended_at = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
    sp = Span(
        id=sid,
        run_id=run_id,
        parent_span_id=parent_span_id,
        kind=kind,
        name=name,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
        metadata_json=metadata_json,
    )
    return sp


def _duration_ms(spans: list[Span], run_id: str) -> float:
    """Compute total run duration from span start/end times."""
    if not spans:
        return 0.0
    starts = [sp.started_at for sp in spans if sp.run_id == run_id]
    ends = [sp.ended_at for sp in spans if sp.run_id == run_id and sp.ended_at]
    if not starts or not ends:
        return 0.0
    return (max(ends) - min(starts)).total_seconds() * 1000


# ---------------------------------------------------------------------------
# Test 1: Two identical runs → all spans in_both
# ---------------------------------------------------------------------------

def test_identical_runs():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="search", kind="tool"),
        _span("a3", name="llm_call", kind="llm"),
    ]
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="search", kind="tool"),
        _span("b3", name="llm_call", kind="llm"),
    ]
    result = diff_runs(spans_a, spans_b, 1000.0, 1000.0)

    assert result.only_in_a == 0
    assert result.only_in_b == 0
    assert result.in_both == 3
    assert all(ds.diff_status == "in_both" for ds in result.spans_a)
    assert all(ds.diff_status == "in_both" for ds in result.spans_b)


# ---------------------------------------------------------------------------
# Test 2: Run B drops one span from A → that span only_in_a
# ---------------------------------------------------------------------------

def test_dropped_span():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="search", kind="tool"),
        _span("a3", name="synthesize", kind="custom"),
    ]
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="search", kind="tool"),
    ]
    result = diff_runs(spans_a, spans_b, 1000.0, 800.0)

    assert result.only_in_a == 1
    assert result.only_in_b == 0
    assert result.in_both == 2

    statuses_a = {ds.span.name: ds.diff_status for ds in result.spans_a}
    assert statuses_a["synthesize"] == "only_in_a"
    assert statuses_a["plan"] == "in_both"
    assert statuses_a["search"] == "in_both"


# ---------------------------------------------------------------------------
# Test 3: Run B adds one span A doesn't have → only_in_b
# ---------------------------------------------------------------------------

def test_added_span():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="search", kind="tool"),
    ]
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="search", kind="tool"),
        _span("b3", name="verify", kind="custom"),
    ]
    result = diff_runs(spans_a, spans_b, 800.0, 1000.0)

    assert result.only_in_a == 0
    assert result.only_in_b == 1
    assert result.in_both == 2

    statuses_b = {ds.span.name: ds.diff_status for ds in result.spans_b}
    assert statuses_b["verify"] == "only_in_b"


# ---------------------------------------------------------------------------
# Test 4: Reordered siblings → still matched by (name, kind, depth, idx)
# ---------------------------------------------------------------------------

def test_reordered_siblings():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="search", kind="tool"),
        _span("a3", name="synthesize", kind="custom"),
    ]
    # Same spans, different order
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="synthesize", kind="custom"),
        _span("b3", name="search", kind="tool"),
    ]
    result = diff_runs(spans_a, spans_b, 1000.0, 1000.0)

    # All root-level spans match by (name, kind, depth=0, sibling_idx)
    # But sibling_idx is computed in started_at order within each run.
    # Since spans in A: plan(idx=0), search(idx=0), synthesize(idx=1)
    # And spans in B: plan(idx=0), synthesize(idx=0), search(idx=0)
    # The search/tool span in A has idx=0 (only tool) and search/tool in B also idx=0
    # plan/custom idx=0 in both, synthesize/custom idx depends on sibling count
    assert result.only_in_a == 0
    assert result.only_in_b == 0
    assert result.in_both == 3


# ---------------------------------------------------------------------------
# Test 5: Two siblings of identical name+kind → matched by sibling index
# ---------------------------------------------------------------------------

def test_duplicate_name_kind_siblings():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="llm_call", kind="llm"),
        _span("a3", name="llm_call", kind="llm"),
    ]
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="llm_call", kind="llm"),
        _span("b3", name="llm_call", kind="llm"),
    ]
    result = diff_runs(spans_a, spans_b, 1000.0, 1000.0)

    assert result.only_in_a == 0
    assert result.only_in_b == 0
    assert result.in_both == 3

    # First llm_call in A should match first llm_call in B
    a_llm = [ds for ds in result.spans_a if ds.span.name == "llm_call"]
    b_llm = [ds for ds in result.spans_b if ds.span.name == "llm_call"]
    assert a_llm[0].partner_id == b_llm[0].span.id
    assert a_llm[1].partner_id == b_llm[1].span.id


# ---------------------------------------------------------------------------
# Test 6: Empty A, populated B → all only_in_b
# ---------------------------------------------------------------------------

def test_empty_vs_populated():
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="search", kind="tool"),
    ]
    result = diff_runs([], spans_b, 0.0, 1000.0)

    assert result.only_in_a == 0
    assert result.only_in_b == 2
    assert result.in_both == 0
    assert len(result.spans_a) == 0
    assert all(ds.diff_status == "only_in_b" for ds in result.spans_b)


# ---------------------------------------------------------------------------
# Test 7: Aggregate stats — durations, costs, tokens
# ---------------------------------------------------------------------------

def test_aggregate_stats():
    spans_a = [
        _span("a1", name="plan", kind="custom"),
        _span("a2", name="llm_1", kind="llm",
              metadata_json='{"model":"gpt-4o","prompt_tokens":100,"completion_tokens":200,"cost_usd":0.005}'),
        _span("a3", name="llm_2", kind="llm",
              metadata_json='{"model":"gpt-4o","prompt_tokens":50,"completion_tokens":100,"cost_usd":0.002}'),
    ]
    spans_b = [
        _span("b1", name="plan", kind="custom"),
        _span("b2", name="llm_1", kind="llm",
              metadata_json='{"model":"gpt-4o","prompt_tokens":100,"completion_tokens":150,"cost_usd":0.004}'),
    ]
    result = diff_runs(spans_a, spans_b, 2000.0, 1500.0)

    assert result.duration_a_ms == 2000.0
    assert result.duration_b_ms == 1500.0
    assert result.cost_a_usd == pytest.approx(0.007, abs=0.0001)
    assert result.cost_b_usd == pytest.approx(0.004, abs=0.0001)
    assert result.tokens_a == 450
    assert result.tokens_b == 250


# ---------------------------------------------------------------------------
# Test 8: Nested spans with parent-child — depth computed correctly
# ---------------------------------------------------------------------------

def test_nested_depth():
    spans_a = [
        _span("a1", name="agent", kind="agent", parent_span_id=None),
        _span("a2", name="search", kind="tool", parent_span_id="a1"),
        _span("a3", name="llm", kind="llm", parent_span_id="a2"),
    ]
    spans_b = [
        _span("b1", name="agent", kind="agent", parent_span_id=None),
        _span("b2", name="search", kind="tool", parent_span_id="b1"),
        _span("b3", name="llm", kind="llm", parent_span_id="b2"),
    ]
    result = diff_runs(spans_a, spans_b, 1000.0, 1000.0)

    assert result.in_both == 3
    depths_a = {ds.span.name: ds.depth for ds in result.spans_a}
    assert depths_a["agent"] == 0
    assert depths_a["search"] == 1
    assert depths_a["llm"] == 2


# ---------------------------------------------------------------------------
# Test 9: No LLM spans → cost/tokens are None
# ---------------------------------------------------------------------------

def test_no_llm_spans():
    spans_a = [_span("a1", name="plan", kind="custom")]
    spans_b = [_span("b1", name="plan", kind="custom")]
    result = diff_runs(spans_a, spans_b, 500.0, 500.0)

    assert result.cost_a_usd is None
    assert result.cost_b_usd is None
    assert result.tokens_a is None
    assert result.tokens_b is None


# ---------------------------------------------------------------------------
# Test 10: partner_id links matched spans bidirectionally
# ---------------------------------------------------------------------------

def test_partner_id_bidirectional():
    spans_a = [_span("a1", name="plan", kind="custom")]
    spans_b = [_span("b1", name="plan", kind="custom")]
    result = diff_runs(spans_a, spans_b, 500.0, 500.0)

    assert result.spans_a[0].partner_id == "b1"
    assert result.spans_b[0].partner_id == "a1"
