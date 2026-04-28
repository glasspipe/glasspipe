"""@trace decorator and span() context manager."""
import functools
import sys
from contextvars import ContextVar
from typing import Any

from nanoid import generate as nanoid_generate

from glasspipe import storage

_current_run_id: ContextVar[str | None] = ContextVar("glasspipe_run_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("glasspipe_span_id", default=None)


def _new_id() -> str:
    return nanoid_generate(size=12)


def _safe_write(fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        print(f"glasspipe warning: storage error ({type(exc).__name__}: {exc})", file=sys.stderr)


# ---------------------------------------------------------------------------
# @trace decorator
# ---------------------------------------------------------------------------

def trace(fn=None, *, name: str | None = None):
    """Decorator that records a function call as a run in the trace DB.

    Supports both ``@trace`` and ``@trace(name="custom")`` call styles.
    """
    if fn is None:
        # Called as @trace(name=...) — return the real decorator
        def decorator(func):
            return _make_wrapper(func, name or func.__name__)
        return decorator

    # Called as @trace (no parentheses)
    return _make_wrapper(fn, name or fn.__name__)


def _make_wrapper(fn, run_name: str):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        run_id = _new_id()
        _safe_write(storage.write_run_start, run_id, run_name)
        token = _current_run_id.set(run_id)
        status = "ok"
        error_message = None
        try:
            result = fn(*args, **kwargs)
            return result
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            _safe_write(storage.write_run_end, run_id, status, error_message)
            _current_run_id.reset(token)

    return wrapper


# ---------------------------------------------------------------------------
# span() context manager
# ---------------------------------------------------------------------------

class SpanContext:
    def __init__(self, name: str, kind: str) -> None:
        self._name = name
        self._kind = kind
        self._span_id: str = _new_id()
        self._run_id: str | None = None
        self._parent_span_id: str | None = None
        self._token = None
        self._input: Any = None
        self._output: Any = None
        self._metadata: Any = None

    def record(self, input: Any = None, output: Any = None, metadata: Any = None) -> None:
        self._input = input
        self._output = output
        self._metadata = metadata

    def __enter__(self) -> "SpanContext":
        run_id = _current_run_id.get()
        if run_id is None:
            raise RuntimeError("span() must be called inside a @trace-decorated function")
        self._run_id = run_id
        self._parent_span_id = _current_span_id.get()
        _safe_write(
            storage.write_span_start,
            self._span_id,
            self._run_id,
            self._parent_span_id,
            self._kind,
            self._name,
        )
        self._token = _current_span_id.set(self._span_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        _current_span_id.reset(self._token)
        status = "error" if exc_type is not None else "ok"
        error_message = str(exc_val) if exc_val is not None else None
        _safe_write(
            storage.write_span_end,
            self._span_id,
            status,
            self._input,
            self._output,
            self._metadata,
            error_message,
        )
        return False  # never suppress exceptions


def span(name: str, kind: str = "custom") -> SpanContext:
    return SpanContext(name, kind)
