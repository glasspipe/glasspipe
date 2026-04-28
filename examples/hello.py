from glasspipe import trace, span


@trace
def my_first_agent(question):
    with span("plan", kind="custom") as s:
        plan = f"I will answer: {question}"
        s.record(input={"question": question}, output={"plan": plan})
    with span("respond", kind="custom") as s:
        answer = "42"
        s.record(input={"plan": plan}, output={"answer": answer})
    return answer


if __name__ == "__main__":
    result = my_first_agent("what is the meaning of life?")
    print(f"Agent returned: {result}")
    print(f"Trace written to ~/.glasspipe/traces.db")
