"""
Live demo: customer support agent BEFORE GlassPipe.

This is a normal Python agent. It reads a customer message, checks account
details, checks refund policy, calls OpenAI to draft a reply, checks the reply,
and returns the final customer response.

Run:
    python examples/live_customer_support_agent_before.py
"""

import json
import os

from openai import OpenAI


MODEL = "gpt-4.1-mini"


def _client() -> OpenAI:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running this demo.")
    return OpenAI()


def customer_support_agent(customer_message: str) -> str:
    customer_problem = {
        "customer_message": customer_message,
        "main_issue": "possible duplicate charge",
        "emotion": "frustrated",
        "priority": "high",
        "goal": "explain what happened and offer the right next step",
    }

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

    refund_policy = {
        "duplicate_pending_charge": "usually disappears automatically within 24-48 hours",
        "captured_duplicate_charge": "refund immediately",
        "tone_rule": "be calm, specific, and do not blame the customer",
        "escalation_rule": "escalate if two captured charges exist",
    }

    next_action = {
        "decision": "do not refund immediately",
        "reason": "one charge is captured and the duplicate charge is still pending",
        "customer_next_step": "ask the customer to wait 24-48 hours and contact support if both charges settle",
        "escalate_to_human": False,
    }

    client = _client()
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
                    + json.dumps(
                        {
                            "customer_problem": customer_problem,
                            "customer_account": customer_account,
                            "refund_policy": refund_policy,
                            "next_action": next_action,
                        },
                        indent=2,
                    )
                ),
            },
        ],
    ).choices[0].message.content

    quality_check = {
        "mentions_pending_charge": "yes",
        "explains_next_step": "yes",
        "tone": "calm and helpful",
        "safe_to_send": True,
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
                    + json.dumps(
                        {"draft": draft, "quality_check": quality_check},
                        indent=2,
                    )
                ),
            },
        ],
    ).choices[0].message.content

    return final_reply


if __name__ == "__main__":
    message = "I was charged twice yesterday and I am really frustrated. Can you fix this?"
    print(customer_support_agent(message))
