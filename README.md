# GlassPipe — The Flight Recorder for AI Agents

**See what your AI agent actually did. Share the trace in one click.**

```bash
pip install glasspipe
```

---

## The problem

You built an AI agent. It takes 47 seconds and costs $3 per run. You have no idea why.

The logs look like soup. You add print statements. You still don't know. You're flying blind.

GlassPipe fixes this in 60 seconds.

---

## How it works

Add one decorator:

```python
from glasspipe import trace

@trace
def my_agent(question):
    # your existing code, completely untouched
    return answer
```

Run your agent. Then:

```bash
glasspipe dashboard
```

Every LLM call, every tool, every step — captured and laid out as a visual timeline. Click any span to see exactly what went in and what came out. Share the whole trace with one click.

---

## Install

```bash
pip install glasspipe
```

Requires Python 3.10+. No account. No API key. No configuration.

---

## Quickstart

```python
from glasspipe import trace, span

@trace
def research_agent(topic):
    # Manual spans for your own steps
    with span("plan", kind="custom") as s:
        plan = f"I will research: {topic}"
        s.record(input={"topic": topic}, output={"plan": plan})

    # Tool calls
    with span("web_search", kind="tool") as s:
        results = ["Result 1", "Result 2"]
        s.record(input={"query": topic}, output={"results": results})

    return results

research_agent("AI agent observability")
```

Then open the dashboard:

```bash
glasspipe dashboard
```

Your trace is waiting at `http://localhost:3000`.

---

## Auto-instrumentation

GlassPipe automatically records every OpenAI and Anthropic call — no extra code needed:

```python
import openai
from glasspipe import trace

@trace
def my_agent(question):
    # This call is automatically captured — model, tokens, cost, latency
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content
```

What gets captured automatically:
- Model name
- Prompt and completion tokens
- Cost in USD
- Latency
- Full input and output

---

## Sharing a trace

In the dashboard, click **Share** on any run.

A preview modal shows you exactly what will be made public. GlassPipe scans for secrets — API keys, tokens, emails, JWTs — and highlights them. Redact anything with one click. Then confirm.

You get a link like:

```
https://glasspipe.dev/t/a1f9c2
```

Anyone can open it. No account needed. Ever. Traces expire after 30 days. You get a delete token to remove it early.

---

## Example traces

- [Simple research agent](#) — 3 spans, plan → search → synthesize
- [Customer support agent](#) — 4 spans, classify → fetch → draft → review

*(Replace these with real shared trace URLs after you run the examples)*

---

## GlassPipe vs Langfuse vs LangSmith

We're going to be honest with you. Pick the right tool.

| | GlassPipe | Langfuse | LangSmith |
|---|---|---|---|
| Install time | ~60 seconds | ~20 minutes | ~20 minutes |
| Account required | Never | Yes | Yes |
| Share a trace publicly | One click | Several steps | Several steps |
| Local dashboard | Yes | No | No |
| Team workspaces | No | Yes | Yes |
| Production monitoring | No | Yes | Yes |
| Async support | No | Yes | Yes |
| Price | Free, open source | Free tier + paid | Free tier + paid |

**Use GlassPipe if:** you're an indie dev or student who wants to install in 60 seconds, see what your agent is doing, and share a trace link without making an account.

**Use Langfuse or LangSmith if:** you need production monitoring, team features, async support, or enterprise observability.

We're not trying to replace them. We're built for a different moment.

---

## Limitations — please read before installing

GlassPipe v1 is intentionally minimal. It does **not**:

- Support async Python (sync only — coming in v1.5)
- Capture streaming responses (final results only)
- Auto-instrument LangChain (raw OpenAI and Anthropic SDKs only)
- Support languages other than Python
- Provide team accounts, alerts, or production monitoring

If you need those things today, use Langfuse, LangSmith, or Arize Phoenix — they're genuinely great tools. GlassPipe is for the 60-second install crowd.

---

## Examples

Three working examples in the `/examples` folder:

```bash
python examples/hello.py            # minimal — one span
python examples/research_agent.py   # 3 spans — plan, search, synthesize
python examples/customer_support.py # 4 spans — classify, fetch, draft, review
```

All examples run without a real API key.

---

## Privacy and security

- Redaction happens on your machine, before upload. The server never sees your original data.
- The pre-share preview modal cannot be bypassed.
- Add custom redaction patterns via `GLASSPIPE_REDACT_PATTERNS` environment variable.
- Shared traces are public but unlisted — accessible only via direct link.
- All shared traces expire after 30 days.

---

## Built with

- Python 3.10+
- Flask + HTMX (local dashboard)
- SQLite (local storage)
- SQLAlchemy
- Railway + Postgres (hosted share service)

---

## License

MIT. Free forever.

---

## Contributing

Issues and PRs welcome. This is a v1 — there's plenty to improve.

---

*Built by Jonathan — [LinkedIn](#) · [glasspipe.dev](#)*

*(Replace # links with your real LinkedIn URL and domain once live)*
