"""
GlassPipe example — research_agent.py

A multi-step research agent that demonstrates how GlassPipe captures
a full trace with multiple spans across different kinds of work.

No API key required — LLM calls are simulated.

Run:
    python examples/research_agent.py

Then open the dashboard to see the trace:
    glasspipe dashboard
"""
from glasspipe import trace, span


@trace
def research_agent(topic: str) -> str:
    # Step 1: plan what to do
    with span("plan", kind="custom") as s:
        plan = f"I will research '{topic}' by searching and synthesizing sources."
        s.record(
            input={"topic": topic},
            output={"plan": plan},
        )

    # Step 2: search (simulated tool call — would be a real API in production)
    with span("web_search", kind="tool") as s:
        results = [
            f"Result 1: {topic} is a rapidly evolving field with broad applications.",
            f"Result 2: Recent advances in {topic} include improved tooling and observability.",
            f"Result 3: Practitioners working with {topic} report significant productivity gains.",
        ]
        s.record(
            input={"query": topic, "num_results": 3},
            output={"results": results, "source": "simulated"},
        )

    # Step 3: synthesize (simulated LLM call — would be openai/anthropic in production)
    with span("synthesize", kind="custom") as s:
        summary = (
            f"Based on research: {topic} is important because it enables developers "
            "to observe and debug AI agent behaviour with minimal code changes. "
            "Key benefits include reduced debugging time and shareable traces."
        )
        s.record(
            input={"results": results, "style": "concise"},
            output={"summary": summary, "word_count": len(summary.split())},
        )

    return summary


if __name__ == "__main__":
    print("Running research agent...")
    result = research_agent("AI agent observability")
    print(f"\nResult:\n{result}")
    print("\nRun 'glasspipe dashboard' to see the trace.")
