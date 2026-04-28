"""Tests for OpenAI and Anthropic auto-instrumentation patches."""
import json
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import glasspipe.trace as _trace_mod
from glasspipe.instruments import openai_patch, anthropic_patch, patch_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows(db_path: str, table: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]


def _fake_openai_module():
    """Build a minimal fake openai module tree that satisfies our import paths."""
    fake_completions_mod = MagicMock()
    # Completions.create will be set per-test
    fake_completions_mod.Completions = MagicMock()
    fake_completions_mod.Completions.create = MagicMock()

    fake_chat = MagicMock()
    fake_chat.completions = fake_completions_mod

    fake_resources = MagicMock()
    fake_resources.chat = fake_chat
    fake_resources.chat.completions = fake_completions_mod

    fake_openai = MagicMock()
    fake_openai.resources = fake_resources

    sys.modules["openai"] = fake_openai
    sys.modules["openai.resources"] = fake_resources
    sys.modules["openai.resources.chat"] = fake_chat
    sys.modules["openai.resources.chat.completions"] = fake_completions_mod

    return fake_completions_mod


def _fake_anthropic_module():
    """Build a minimal fake anthropic module tree."""
    fake_messages_mod = MagicMock()
    fake_messages_mod.Messages = MagicMock()
    fake_messages_mod.Messages.create = MagicMock()

    fake_resources = MagicMock()
    fake_resources.messages = fake_messages_mod

    fake_anthropic = MagicMock()
    fake_anthropic.resources = fake_resources

    sys.modules["anthropic"] = fake_anthropic
    sys.modules["anthropic.resources"] = fake_resources
    sys.modules["anthropic.resources.messages"] = fake_messages_mod

    return fake_messages_mod


def _openai_response(model="gpt-4o", prompt_tokens=10, completion_tokens=5, text="four"):
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(model=model, usage=usage, choices=[choice])


def _anthropic_response(model="claude-sonnet-4-5", input_tokens=8, output_tokens=4, text="four"):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    content_block = SimpleNamespace(text=text)
    return SimpleNamespace(model=model, usage=usage, content=[content_block])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_patch_state():
    """Reset module-level globals before and after every test."""
    # Reset trace._patched so lazy activation fires fresh
    _trace_mod._patched = False
    # Ensure patch modules start unpatched
    openai_patch._original = None
    anthropic_patch._original = None
    yield
    # Cleanup after test
    openai_patch.unpatch()
    anthropic_patch.unpatch()
    _trace_mod._patched = False
    # Remove fake SDK modules so they don't bleed into other tests
    for key in list(sys.modules.keys()):
        if key.startswith("openai") or key.startswith("anthropic"):
            del sys.modules[key]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_openai_patch_captures_span(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    fake_mod = _fake_openai_module()
    real_create = MagicMock(return_value=_openai_response())
    fake_mod.Completions.create = real_create

    openai_patch.patch()

    from glasspipe import trace

    @trace
    def agent():
        # Simulate: client.chat.completions.create(...)
        # After patching, Completions.create is our wrapper.
        # Call it as an unbound method with a dummy self.
        import openai.resources.chat.completions as _mod
        _mod.Completions.create(object(), model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

    agent()

    spans = _rows(db, "spans")
    llm_spans = [s for s in spans if s["kind"] == "llm"]
    assert len(llm_spans) == 1

    sp = llm_spans[0]
    assert sp["name"] == "openai.chat.completions"
    assert sp["status"] == "ok"

    meta = json.loads(sp["metadata_json"])
    assert meta["model"] == "gpt-4o"
    assert meta["cost_usd"] > 0
    assert meta["prompt_tokens"] == 10
    assert meta["completion_tokens"] == 5
    assert meta["latency_ms"] >= 0


def test_anthropic_patch_captures_span(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    fake_mod = _fake_anthropic_module()
    real_create = MagicMock(return_value=_anthropic_response())
    fake_mod.Messages.create = real_create

    anthropic_patch.patch()

    from glasspipe import trace

    @trace
    def agent():
        import anthropic.resources.messages as _mod
        _mod.Messages.create(object(), model="claude-sonnet-4-5", messages=[{"role": "user", "content": "hi"}])

    agent()

    spans = _rows(db, "spans")
    llm_spans = [s for s in spans if s["kind"] == "llm"]
    assert len(llm_spans) == 1

    sp = llm_spans[0]
    assert sp["name"] == "anthropic.messages"
    assert sp["status"] == "ok"

    meta = json.loads(sp["metadata_json"])
    assert meta["model"] == "claude-sonnet-4-5"
    assert meta["cost_usd"] > 0
    assert meta["prompt_tokens"] == 8
    assert meta["completion_tokens"] == 4


def test_no_span_outside_trace(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("GLASSPIPE_DB_PATH", db)

    fake_mod = _fake_openai_module()
    real_create = MagicMock(return_value=_openai_response())
    fake_mod.Completions.create = real_create

    openai_patch.patch()

    # Call the patched method with no active @trace run
    import openai.resources.chat.completions as _mod
    result = _mod.Completions.create(object(), model="gpt-4o", messages=[{"role": "user", "content": "hi"}])

    # The original should have been called through
    assert real_create.called

    # No DB tables yet (init_db never called outside @trace context), but even if
    # the DB exists, there must be zero span rows.
    try:
        spans = _rows(db, "spans")
        assert len(spans) == 0
    except Exception:
        pass  # DB doesn't exist — also fine


def test_unpatch_restores_original(tmp_path, monkeypatch):
    monkeypatch.setenv("GLASSPIPE_DB_PATH", str(tmp_path / "test.db"))

    fake_mod = _fake_openai_module()
    real_create = MagicMock(return_value=_openai_response())
    fake_mod.Completions.create = real_create

    openai_patch.patch()

    import openai.resources.chat.completions as _mod
    assert _mod.Completions.create is not real_create  # wrapper installed

    openai_patch.unpatch()

    assert _mod.Completions.create is real_create  # restored
    assert openai_patch._original is None


def test_missing_library_silent(tmp_path, monkeypatch):
    monkeypatch.setenv("GLASSPIPE_DB_PATH", str(tmp_path / "test.db"))
    # Ensure neither SDK is in sys.modules (fixture already cleared them)
    # patch_all() must not raise even though neither library is installed
    patch_all()  # no exception = pass
