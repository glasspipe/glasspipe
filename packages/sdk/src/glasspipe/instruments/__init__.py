"""Per-provider instrumentation — patches OpenAI and Anthropic SDKs if installed."""
from glasspipe.instruments import openai_patch, anthropic_patch


def patch_all() -> None:
    openai_patch.patch()
    anthropic_patch.patch()
