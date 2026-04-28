import json
import sqlite3

import pytest

from glasspipe import trace, span
from glasspipe import storage as _storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows(db_path: str, table: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_trace_decorator_creates_run(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    @trace
    def simple(x):
        return x * 2

    result = simple(3)
    assert result == 6

    runs = _rows(db, "runs")
    assert len(runs) == 1
    run = runs[0]
    assert run["name"] == "simple"
    assert run["status"] == "ok"
    assert run["ended_at"] is not None


def test_trace_captures_exception(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    @trace
    def boom():
        raise ValueError("something went wrong")

    with pytest.raises(ValueError):
        boom()

    runs = _rows(db, "runs")
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "error"
    assert "something went wrong" in run["error_message"]
    assert run["ended_at"] is not None


def test_span_creates_span_row(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    @trace
    def agent():
        with span("search", kind="tool") as s:
            s.record(input={"query": "hello"}, output={"results": ["a", "b"]})

    agent()

    runs = _rows(db, "runs")
    spans = _rows(db, "spans")
    assert len(runs) == 1
    assert len(spans) == 1

    sp = spans[0]
    assert sp["name"] == "search"
    assert sp["kind"] == "tool"
    assert sp["run_id"] == runs[0]["id"]
    assert json.loads(sp["input_json"]) == {"query": "hello"}
    assert json.loads(sp["output_json"]) == {"results": ["a", "b"]}
    assert sp["status"] == "ok"
    assert sp["ended_at"] is not None


def test_nested_spans_link_correctly(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    @trace
    def agent():
        with span("outer", kind="custom") as outer:
            with span("inner", kind="custom") as inner:
                inner.record(output={"x": 1})
            outer.record(output={"x": 2})

    agent()

    spans = _rows(db, "spans")
    assert len(spans) == 2

    by_name = {s["name"]: s for s in spans}
    outer = by_name["outer"]
    inner = by_name["inner"]

    assert inner["parent_span_id"] == outer["id"]
    assert outer["parent_span_id"] is None


def test_span_outside_trace_raises(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    with pytest.raises(RuntimeError, match="span\\(\\) must be called inside a @trace-decorated function"):
        with span("orphan"):
            pass


def test_db_path_override(tmp_path, monkeypatch):
    custom_db = str(tmp_path / "custom.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", custom_db)

    @trace
    def noop():
        pass

    noop()

    # custom path was used
    runs = _rows(custom_db, "runs")
    assert len(runs) == 1

    # default path was NOT created
    import os
    default = os.path.expanduser("~/.glasspipe/traces.db")
    # We can't assert the default doesn't exist (it may from earlier manual runs),
    # but we can assert our custom DB has exactly the run we just wrote.
    assert runs[0]["name"] == "noop"
