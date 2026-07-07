"""Seed realistic sample traces so the dashboard has something to show.

Used by `glasspipe demo`. No API keys, no network — LLM spans carry simulated
but realistic token counts and real pricing so cost views render properly.
"""
import time

from glasspipe.trace import trace, span

_GPT4O_IN = 2.50 / 1_000_000
_GPT4O_OUT = 10.00 / 1_000_000
_HAIKU_IN = 0.80 / 1_000_000
_HAIKU_OUT = 4.00 / 1_000_000


def _llm(name, model, prompt_tokens, completion_tokens, in_price, out_price,
         input_data, output_text, sleep=0.12):
    with span(name, kind="llm") as s:
        time.sleep(sleep)
        s.record(
            input=input_data,
            output={"text": output_text},
            metadata={
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": round(sleep * 1000, 1),
                "cost_usd": round(
                    prompt_tokens * in_price + completion_tokens * out_price, 8
                ),
            },
        )


def _research_agent_impl(topic: str, thorough: bool) -> str:
    with span("plan", kind="custom") as s:
        time.sleep(0.03)
        steps = ["search", "read sources", "synthesize", "write summary"]
        s.record(input={"topic": topic}, output={"steps": steps})

    with span("web_search", kind="tool") as s:
        time.sleep(0.09)
        results = [
            {"title": "AI agent observability in 2026", "url": "https://example.com/a"},
            {"title": "Tracing LLM pipelines", "url": "https://example.com/b"},
            {"title": "Why agents fail silently", "url": "https://example.com/c"},
        ]
        s.record(input={"query": topic}, output={"results": results})

    sources = results[:3] if thorough else results[:1]
    for r in sources:
        with span("fetch_page", kind="tool") as s:
            time.sleep(0.06)
            s.record(input={"url": r["url"]}, output={"chars": 18432, "title": r["title"]})

    _llm(
        "synthesize", "gpt-4o", 2210 if thorough else 910, 240,
        _GPT4O_IN, _GPT4O_OUT,
        {"topic": topic, "sources": [r["url"] for r in sources]},
        "Agent observability has consolidated around trace-first workflows…",
        sleep=0.28 if thorough else 0.16,
    )

    with span("write_summary", kind="custom") as s:
        time.sleep(0.03)
        summary = f"3 key findings on {topic} (see synthesized brief)."
        s.record(input={"format": "markdown"}, output={"summary": summary})
    return summary


research_agent_v1 = trace(name="research_agent", version="v1.2.0")(
    lambda topic: _research_agent_impl(topic, thorough=True)
)
research_agent_v2 = trace(name="research_agent", version="v1.3.0")(
    lambda topic: _research_agent_impl(topic, thorough=False)
)


@trace(name="support_agent")
def support_agent(ticket: str, fail: bool = False) -> str:
    _llm(
        "classify_intent", "claude-haiku-4-5", 340, 18,
        _HAIKU_IN, _HAIKU_OUT,
        {"ticket": ticket},
        '{"intent": "billing.duplicate_charge", "priority": "high"}',
        sleep=0.07,
    )

    with span("fetch_account", kind="tool") as s:
        time.sleep(0.05)
        if fail:
            s.record(input={"customer_id": "cus_1042"})
            raise ConnectionError("billing service timeout after 3 retries")
        account = {
            "customer_id": "cus_1042",
            "plan": "Pro",
            "recent_charges": [
                {"amount": "$49", "status": "captured"},
                {"amount": "$49", "status": "pending"},
            ],
        }
        s.record(input={"customer_id": "cus_1042"}, output=account)

    _llm(
        "draft_reply", "gpt-4o", 1180, 160,
        _GPT4O_IN, _GPT4O_OUT,
        {"ticket": ticket, "account": account},
        "Hi — the second $49 charge is a pending authorization and will drop off…",
        sleep=0.21,
    )

    with span("quality_gate", kind="custom") as s:
        time.sleep(0.02)
        s.record(
            input={"checks": ["tone", "facts", "next steps"]},
            output={"safe_to_send": True},
        )
    return "reply sent"


def seed_demo_traces() -> int:
    """Create sample runs; returns how many were written."""
    count = 0

    research_agent_v1("AI agent observability")
    count += 1

    research_agent_v2("AI agent observability")
    count += 1

    support_agent("I was charged twice yesterday, please fix this.")
    count += 1

    try:
        support_agent("Why did my export fail?", fail=True)
    except ConnectionError:
        pass  # intentional — demonstrates error capture
    count += 1

    return count
