"""Monkey-patch for anthropic.resources.messages.Messages.create (sync only)."""
import time

from glasspipe.trace import _current_run_id, _current_span_id, _new_id, _safe_write
from glasspipe import storage

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-5":   (15.00, 75.00),
    "claude-sonnet-4-5": (3.00,  15.00),
    "claude-haiku-4-5":  (0.80,   4.00),
    "claude-3-5-sonnet": (3.00,  15.00),
    "claude-3-5-haiku":  (0.80,   4.00),
    "claude-3-opus":     (15.00, 75.00),
    "claude-3-haiku":    (0.25,   1.25),
}


def _normalize_model(model: str) -> str:
    if not model:
        return model
    base = model.split("-202")[0].split("-2024")[0].split("-2025")[0]
    if base.startswith("claude-3-5-"):
        base = "claude-3-5-" + base.split("claude-3-5-")[1].split("-202")[0]
    return base

_original = None


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = _PRICING.get(model, _PRICING.get(_normalize_model(model), (0.0, 0.0)))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


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
            span_id, run_id, parent_span_id, "llm", "anthropic.messages",
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

            input_tokens = 0
            output_tokens = 0
            output_text = None
            if response is not None:
                try:
                    usage = response.usage
                    input_tokens = usage.input_tokens
                    output_tokens = usage.output_tokens
                    model = response.model or model
                    output_text = response.content[0].text
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
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "cost_usd": _compute_cost(model, input_tokens, output_tokens),
                },
                error_message,
            )

    return wrapper


def patch() -> None:
    global _original
    if _original is not None:
        return
    try:
        import anthropic.resources.messages as _mod
        _original = _mod.Messages.create
        _mod.Messages.create = _make_wrapper(_original)
    except ImportError:
        pass


def unpatch() -> None:
    global _original
    if _original is None:
        return
    try:
        import anthropic.resources.messages as _mod
        _mod.Messages.create = _original
        _original = None
    except ImportError:
        pass
