# GlassPipe — hello.py
#
# REAL USAGE (with an actual OpenAI key):
#
#   import openai
#   from glasspipe import trace
#
#   @trace
#   def my_agent(question):
#       client = openai.OpenAI()
#       response = client.chat.completions.create(
#           model="gpt-4o-mini",
#           messages=[{"role": "user", "content": question}],
#       )
#       return response.choices[0].message.content
#
#   my_agent("what is 2+2?")
#
# GlassPipe automatically captures the LLM call as a child span — no extra code
# needed. Check ~/.glasspipe/traces.db to see model, tokens, cost, and latency.

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


@trace
def agent_with_llm(question):
    # Demonstrates the instrumentation shape without a real API key.
    # In production, replace this span body with a real openai/anthropic call
    # and GlassPipe will capture it automatically.
    with span("think", kind="custom") as s:
        s.record(input={"q": question}, output={"thought": "use llm"})
    return "answer"


if __name__ == "__main__":
    result = my_first_agent("what is the meaning of life?")
    print(f"my_first_agent returned: {result}")

    result2 = agent_with_llm("what is 2+2?")
    print(f"agent_with_llm returned: {result2}")

    print("Traces written to ~/.glasspipe/traces.db")
