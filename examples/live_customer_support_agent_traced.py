"""
Live demo: customer support agent WITH GlassPipe.

This is the same customer support agent, now instrumented with GlassPipe.
The only core idea is:

1. Import trace and span.
2. Put @trace above the main agent function.
3. Use optional span blocks to label important steps in the waterfall.

Run:
    GLASSPIPE_DB_PATH=/private/tmp/glasspipe-interview-test.db python examples/live_customer_support_agent_traced.py
"""

import json
import os

from openai import OpenAI

from glasspipe import trace, span


MODEL = "gpt-4.1-mini"


def _client() -> OpenAI:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running this demo.")
    return OpenAI()


@trace(name="live_customer_support_agent")
def customer_support_agent(customer_message: str) -> str:
    with span("read_customer_message", kind="tool") as s:
        raw_message = {
            "source": "support inbox",
            "message": customer_message,
        }
        s.record(input={"new_ticket": True}, output=raw_message)

    with span("understand_customer_problem", kind="custom") as s:
        customer_problem = {
            "customer_message": customer_message,
            "main_issue": "possible duplicate charge",
            "emotion": "frustrated",
            "priority": "high",
            "goal": "explain what happened and offer the right next step",
        }
        s.record(input=raw_message, output=customer_problem)

    with span("look_up_customer_account", kind="tool") as s:
        customer_account = {
            "customer_id": "cus_1042",
            "plan": "Pro",
            "monthly_price": "$49",
            "recent_charges": [
                {"date": "yesterday", "amount": "$49", "status": "captured"},
                {"date": "yesterday", "amount": "$49", "status": "pending"},
            ],
            "support_history": "first billing complaint",
        }
        s.record(
            input={"customer_id": customer_account["customer_id"]},
            output=customer_account,
        )

    with span("check_refund_policy", kind="tool") as s:
        refund_policy = {
            "duplicate_pending_charge": "usually disappears automatically within 24-48 hours",
            "captured_duplicate_charge": "refund immediately",
            "tone_rule": "be calm, specific, and do not blame the customer",
            "escalation_rule": "escalate if two captured charges exist",
        }
        s.record(
            input={"issue": customer_problem["main_issue"], "plan": customer_account["plan"]},
            output=refund_policy,
        )

    with span("decide_next_action", kind="custom") as s:
        next_action = {
            "decision": "do not refund immediately",
            "reason": "one charge is captured and the duplicate charge is still pending",
            "customer_next_step": "ask the customer to wait 24-48 hours and contact support if both charges settle",
            "escalate_to_human": False,
        }
        s.record(
            input={
                "recent_charges": customer_account["recent_charges"],
                "refund_policy": refund_policy,
            },
            output=next_action,
        )

    client = _client()

    with span("draft_customer_reply", kind="custom") as s:
        draft_prompt_data = {
            "customer_problem": customer_problem,
            "customer_account": customer_account,
            "refund_policy": refund_policy,
            "next_action": next_action,
        }
        draft = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful SaaS customer support agent.",
                },
                {
                    "role": "user",
                    "content": (
                        "Draft a support reply using this context. Be helpful, concrete, "
                        "and under 130 words.\n\n"
                        + json.dumps(draft_prompt_data, indent=2)
                    ),
                },
            ],
        ).choices[0].message.content
        s.record(input=draft_prompt_data, output={"draft_reply": draft})

    with span("quality_check_reply", kind="custom") as s:
        quality_check = {
            "mentions_pending_charge": "yes",
            "explains_next_step": "yes",
            "tone": "calm and helpful",
            "safe_to_send": True,
        }
        s.record(input={"draft_reply": draft}, output=quality_check)

    with span("final_customer_reply", kind="custom") as s:
        final_prompt_data = {
            "draft": draft,
            "quality_check": quality_check,
        }
        final_reply = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You polish customer support replies without changing facts.",
                },
                {
                    "role": "user",
                    "content": (
                        "Polish this reply using the quality check.\n\n"
                        + json.dumps(final_prompt_data, indent=2)
                    ),
                },
            ],
        ).choices[0].message.content
        s.record(input=final_prompt_data, output={"final_reply": final_reply})

    return final_reply


if __name__ == "__main__":
    message = "I was charged twice yesterday and I am really frustrated. Can you fix this?"
    print(customer_support_agent(message))
