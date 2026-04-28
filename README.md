# GlassPipe

**The flight recorder for AI agents.** Decorate a function, run it, see every span in a waterfall timeline. Share the trace in one click — no account required.

---

## Install

```bash
pip install glasspipe
```

## 60-second quickstart

```python
from glasspipe import trace, span

@trace
def my_agent(question):
    with span("plan", kind="custom") as s:
        plan = f"I will answer: {question}"
        s.record(input={"question": question}, output={"plan": plan})
    return plan

my_agent("what is the meaning of life?")
```

Run it. That's it — the trace is written to `~/.glasspipe/traces.db`.

## View the trace

```bash
glasspipe dashboard   # opens http://localhost:3000
```

Click a run to see the waterfall timeline. Click a span to inspect its input, output, and metadata.

## Share a trace

Open any run in the dashboard and click **Share**. GlassPipe shows you everything that will be public (secrets are auto-redacted), then generates a link at `glasspipe.dev/t/<id>` — no account, no signup.

## Auto-instrument OpenAI / Anthropic

LLM calls inside a `@trace` function are captured automatically — model, token counts, cost, and latency appear as child spans with no extra code:

```python
import openai
from glasspipe import trace

@trace
def ask(question):
    client = openai.OpenAI()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": question}],
    )
    return r.choices[0].message.content

ask("what is 2+2?")
# → one run row, one llm span with tokens + cost in the dashboard
```

## Development

```bash
git clone https://github.com/glasspipe/glasspipe
cd glasspipe
python -m venv .venv && source .venv/bin/activate
pip install -e "packages/sdk[dev,dashboard]"

# Run tests
pytest packages/sdk/tests/ -v

# Run dashboard
glasspipe dashboard

# Run hosted API locally (uses SQLite instead of Postgres)
DATABASE_URL=sqlite:///shares.db python packages/api/app.py
```

## License

MIT — see [LICENSE](./LICENSE).
