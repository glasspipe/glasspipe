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

Anyone can open it. No account, ever. Traces expire after 30 days. You get a delete token to remove a trace early.

**Privacy guarantees:**

- Redaction happens on your machine, before upload. The server never sees the original data.
- The pre-share preview cannot be bypassed.
- Custom redaction patterns: set `GLASSPIPE_REDACT_PATTERNS` as a JSON dict in your environment.
- Shared traces are public but unlisted — accessible only by direct link.

---

## `[ EXAMPLES ]` Examples

Three working examples in the [`/examples`](examples/) folder:

```bash
python examples/hello.py             # minimal — one span
python examples/research_agent.py    # 3 spans: plan, search, synthesize
python examples/customer_support.py  # 4 spans: classify, fetch, draft, review
```

All three run without a real API key.

---

## `[ COMPARE ]` GlassPipe vs Langfuse vs LangSmith

Honest comparison. Pick the right tool for the job.

|                           | GlassPipe      | Langfuse         | LangSmith        |
| ------------------------- | -------------- | ---------------- | ---------------- |
| Install time              | ~60 seconds    | ~20 minutes      | ~20 minutes      |
| Account required          | Never          | Yes              | Yes              |
| Public share in one click | Yes            | No               | No               |
| Local dashboard           | Yes            | No               | No               |
| Team workspaces           | No             | Yes              | Yes              |
| Production monitoring     | No             | Yes              | Yes              |
| Async support             | No             | Yes              | Yes              |
| Price                     | Free, OSS      | Free tier + paid | Free tier + paid |

---

## `[ LIMITS ]` What v1 doesn't do

We'd rather you know now than discover it ten minutes in. v1 is intentionally minimal. It does **not**:

- Support async Python (sync only — coming in v1.5)
- Capture streaming responses (final results only)
- Auto-instrument LangChain (raw OpenAI and Anthropic SDKs only)
- Support languages other than Python
- Provide team accounts, alerting, or production monitoring

If you need any of these today, use Langfuse, LangSmith, or Arize Phoenix. They're genuinely great tools.

---

## `[ DEV ]` Built with

Python 3.10+ · Flask · HTMX · SQLite · SQLAlchemy  
Hosted share service: Railway + Postgres

---

## `[ LIC ]` License

MIT. Free forever. See [LICENSE](LICENSE).

---

## `[ CTRB ]` Contributing

Issues and PRs welcome. This is v1 — there's plenty to improve.

- [Open an issue](https://github.com/glasspipe/glasspipe/issues)
- [Start a discussion](https://github.com/glasspipe/glasspipe/discussions)

---

Built by [Yonatan Michelson](https://www.linkedin.com/in/yonatan-michelson) · [glasspipe.dev](https://glasspipe.dev)
