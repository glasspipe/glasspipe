"""
GlassPipe example — customer_support.py

A customer support agent that classifies an incoming request, fetches
a relevant knowledge base article, drafts a response, and checks
its quality before sending.

Shows a tool span (fetch_kb_article) alongside custom spans — produces
a 4-span waterfall with orange and green bars in the dashboard.

No API key required — all steps are simulated.

Run:
    python examples/customer_support.py

Then open the dashboard to see the trace:
    glasspipe dashboard
"""
from glasspipe import trace, span


@trace
def support_agent(customer_message: str) -> str:
    # Step 1: classify the intent
    with span("classify_intent", kind="custom") as s:
        intent = "billing_question" if "charge" in customer_message.lower() else "general_inquiry"
        confidence = 0.94
        s.record(
            input={"message": customer_message},
            output={"intent": intent, "confidence": confidence},
        )

    # Step 2: fetch a knowledge base article (tool call)
    with span("fetch_kb_article", kind="tool") as s:
        article = {
            "id": "KB-1042",
            "title": "Understanding your billing cycle",
            "content": "Charges appear within 2-3 business days of your renewal date.",
            "relevance_score": 0.91,
        }
        s.record(
            input={"intent": intent, "top_k": 1},
            output={"article": article},
        )

    # Step 3: draft a response (simulated LLM call)
    with span("draft_response", kind="custom") as s:
        draft = (
            f"Hi! I understand you have a question about {intent.replace('_', ' ')}. "
            f"{article['content']} "
            "Please don't hesitate to reach out if you need further clarification."
        )
        s.record(
            input={"intent": intent, "article_id": article["id"], "tone": "friendly"},
            output={"draft": draft, "word_count": len(draft.split())},
        )

    # Step 4: quality check before sending
    with span("quality_check", kind="custom") as s:
        checks = {
            "tone": "friendly",
            "has_resolution": True,
            "length_ok": 10 < len(draft.split()) < 100,
            "approved": True,
        }
        s.record(
            input={"draft": draft},
            output=checks,
        )

    return draft


if __name__ == "__main__":
    message = "Why was I charged twice this month?"
    print(f"Customer: {message}\n")
    print("Running support agent...")
    response = support_agent(message)
    print(f"\nAgent response:\n{response}")
    print("\nRun 'glasspipe dashboard' to see the trace.")
