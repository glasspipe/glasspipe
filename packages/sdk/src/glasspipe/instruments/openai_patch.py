"""Monkey-patch for openai.chat.completions.create (sync only)."""
import sys
import time
from typing import Any

from glasspipe.trace import _current_run_id, _current_span_id, _new_id, _safe_write
from glasspipe import storage

_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o":        (2.50,  10.00),
    "gpt-4o-mini":   (0.15,   0.60),
    "gpt-4-turbo":   (10.00, 30.00),
    "gpt-3.5-turbo": (0.50,   1.50),
}

_original = None


def _compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * inp + completion_tokens * out) / 1_000_000


def _make_wrapper(original):
    def wrapper(self, *args, **kwargs):
        if _current_run_id.get() is None:
            return original(self, *args, **kwargs)

        span_id = _new_id()
        run_id = _current_run_id.get()
        parent_span_id = _current_span_id.get()
        messages = kwargs.get("messages") or (args[0] if args else None)
        model = kwargs.get("model") or (args[1] if len(args) > 1 else "unknown")

        _safe_write(
            storage.write_span_start,
            span_id, run_id, parent_span_id, "llm", "openai.chat.completions",
        )
        token = _current_span_id.set(span_id)
        t0 = time.monotonic()
        status = "ok"
        error_message = None
        response = None
        try:
            response = original(self, *args, **kwargs)
            return response
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            _current_span_id.reset(token)

            prompt_tokens = 0
            completion_tokens = 0
            output_text = None
            if response is not None:
                try:
                    usage = response.usage
                    prompt_tokens = usage.prompt_tokens
                    completion_tokens = usage.completion_tokens
                    model = response.model or model
                    output_text = response.choices[0].message.content
                except Exception:
                    pass

            _safe_write(
                storage.write_span_end,
                span_id,
                status,
                messages,
                {"text": output_text},
                {
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "latency_ms": latency_ms,
                    "cost_usd": _compute_cost(model, prompt_tokens, completion_tokens),
                },
                error_message,
            )

    return wrapper


def patch() -> None:
    global _original
    if _original is not None:
        return
    try:
        import openai.resources.chat.completions as _mod
        _original = _mod.Completions.create
        _mod.Completions.create = _make_wrapper(_original)
    except ImportError:
        pass


def unpatch() -> None:
    global _original
    if _original is None:
        return
    try:
        import openai.resources.chat.completions as _mod
        _mod.Completions.create = _original
        _original = None
    except ImportError:
        pass
