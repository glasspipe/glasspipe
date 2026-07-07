from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_customer_support_demo_pair_is_easy_to_explain():
    before = ROOT / "examples" / "live_customer_support_agent_before.py"
    traced = ROOT / "examples" / "live_customer_support_agent_traced.py"

    before_text = before.read_text()
    traced_text = traced.read_text()

    assert "from glasspipe import" not in before_text
    assert "from glasspipe import trace, span" in traced_text
    assert '@trace(name="live_customer_support_agent")' in traced_text

    for label in [
        "read_customer_message",
        "understand_customer_problem",
        "look_up_customer_account",
        "check_refund_policy",
        "decide_next_action",
        "draft_customer_reply",
        "quality_check_reply",
        "final_customer_reply",
    ]:
        assert label in traced_text
