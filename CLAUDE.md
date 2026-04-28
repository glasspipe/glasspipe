# GlassPipe — Project Memory for Claude Code

> Read this file at the start of every session. It contains everything you need
> to know about this project without asking Jonathan to re-explain context.

---

## What this project is

GlassPipe is a Python observability tool — "the flight recorder for AI agents."
Built by Jonathan as a session-based portfolio project (started April 27, 2026).

**Tagline:** "See what your AI agent actually did. Share the trace in one click."

**The three pieces:**
1. `pip install glasspipe` — Python SDK with `@trace` decorator + `span()` context manager
2. `glasspipe dashboard` — local Flask dashboard at localhost:3000 with waterfall timeline
3. Hosted share service — `glasspipe.dev/t/<id>` public trace links, no account required

---

## Current state

- **Last commit:** `548f170` — feat(dashboard): waterfall timeline UI with HTMX span detail panel
- **Test suite:** 12/12 green
- **What works:** @trace, span(), SQLite storage, auto-instrumentation, local dashboard at localhost:3000
- **Next session:** Share service — click Share → mandatory redaction review → public URL at glasspipe.dev/t/\<id\>

---

## Repository layout

```
glasspipe/                          ← repo root, ~/Desktop/glasspipe
├── CLAUDE.md                       ← this file
├── .gitignore
├── LICENSE                         ← MIT, 2026 Jonathan
├── README.md
├── .venv/                          ← shared virtualenv (never commit)
├── docs/
│   └── README.md
├── examples/
│   └── hello.py
└── packages/
    ├── sdk/                        ← the pip-installable library
    │   ├── pyproject.toml          ← hatchling backend, version 0.0.0
    │   └── src/glasspipe/
    │       ├── __init__.py         ← exports: trace, span
    │       ├── trace.py            ← @trace decorator + span() context manager
    │       ├── storage.py          ← SQLAlchemy models + DB write functions
    │       ├── redact.py           ← secret detection (stub until session 10)
    │       ├── share.py            ← upload to api.glasspipe.dev (stub until session 12)
    │       ├── cli.py              ← click CLI (stub until later)
    │       └── instruments/        ← auto-patch openai, anthropic (stub until session 4-5)
    ├── dashboard/                  ← local Flask app, port 5050
    │   ├── app.py
    │   ├── requirements.txt
    │   ├── templates/
    │   └── static/
    ├── api/                        ← hosted Flask share service, port 5051
    │   ├── app.py
    │   └── requirements.txt
    └── web/                        ← static landing page
        ├── index.html
        └── landing-mockup.html     ← design reference, DO NOT modify
```

---

## Tech stack (locked — do not change without asking)

| Layer | Choice | Notes |
|---|---|---|
| SDK language | Python 3.10+ | Jonathan has 3.14.3 locally |
| Build backend | hatchling | modern, src-layout native |
| Local DB | SQLite via SQLAlchemy 2.x | `~/.glasspipe/traces.db` |
| DB path override | `GLASSPIPE_DB_PATH` env var | full file path |
| Dashboard | Flask + HTMX + Tailwind CDN | NOT React |
| Hosted API | Flask + Postgres | Railway deployment |
| Deploy | Railway | free tier |
| Distribution | PyPI | package name: `glasspipe` |
| IDs | nanoid (12 chars) | not UUID |

---

## Hard scope rules for v1 — NEVER add these without explicit permission

```
❌ Async support (sync Python only)
❌ Streaming response capture
❌ User accounts or login
❌ Team features, workspaces, RBAC
❌ Any language other than Python
❌ Frameworks beyond raw OpenAI + Anthropic SDKs (LangChain basic ok in v1.5)
❌ Real-time alerts or notifications
❌ Pricing or billing
❌ LLM-powered "AI insights" on traces
❌ React (HTMX only for dashboard)
❌ Mobile or responsive design
❌ Browser extension
```

If a feature isn't in the current session plan, ASK before adding it.

---

## Data model

```sql
runs
  id              TEXT PK    -- nanoid 12 chars
  name            TEXT       -- function name or @trace(name=...)
  started_at      DATETIME   -- UTC
  ended_at        DATETIME   -- UTC, nullable
  status          TEXT       -- 'running' | 'ok' | 'error'
  error_message   TEXT       -- nullable
  metadata_json   TEXT       -- nullable

spans
  id              TEXT PK    -- nanoid 12 chars
  run_id          TEXT FK    -- references runs.id, indexed
  parent_span_id  TEXT       -- nullable, self-referencing FK
  kind            TEXT       -- 'agent' | 'llm' | 'tool' | 'custom'
  name            TEXT
  started_at      DATETIME   -- UTC
  ended_at        DATETIME   -- UTC, nullable
  status          TEXT       -- 'running' | 'ok' | 'error'
  error_message   TEXT       -- nullable
  input_json      TEXT       -- nullable, JSON-serialized
  output_json     TEXT       -- nullable, JSON-serialized
  metadata_json   TEXT       -- nullable

-- hosted only:
shared_traces
  id              TEXT PK    -- 6 char short ID
  run_data_json   TEXT       -- full run + spans, post-redaction
  created_at      DATETIME
  expires_at      DATETIME   -- created_at + 30 days
  delete_token    TEXT       -- secret for owner-initiated deletion
  view_count      INTEGER
```

---

## Core SDK patterns

### @trace decorator (contextvars approach)
```python
from contextvars import ContextVar

_current_run_id: ContextVar[str | None] = ContextVar('run_id', default=None)
_current_span_id: ContextVar[str | None] = ContextVar('span_id', default=None)
```

- Use `@functools.wraps(fn)` always
- Handle both `@trace` and `@trace(name="foo")` call styles
- Set contextvar token, reset in `finally` block
- Write to DB via `_safe_write()` wrapper — NEVER let storage errors crash user code
- All timestamps: `datetime.now(UTC)` (not `datetime.utcnow()`)

### span() context manager
- Reads `_current_run_id` — if None, raise `RuntimeError("span() must be called inside a @trace function")`
- Reads `_current_span_id` for parent linking
- `.record(input=..., output=...)` stores on object until `__exit__` flushes to DB
- `return False` from `__exit__` — never suppress exceptions

### JSON safety
```python
def safe_json(obj):
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps(repr(obj))
```

---

## How to run things

```bash
# activate virtualenv (always do this first)
source .venv/bin/activate

# install SDK in editable mode (after any pyproject.toml change)
pip install -e packages/sdk

# install dev deps (pytest etc.)
pip install -e "packages/sdk[dev]"

# run tests
pytest packages/sdk/tests/ -v

# run dashboard
python packages/dashboard/app.py   # → localhost:5050

# run API
python packages/api/app.py         # → localhost:5051

# verify SDK import
python -c "from glasspipe import trace, span; print('ok')"
```

---

## Git discipline

- One commit per logical unit of work
- Commit message format: `type(scope): description`
  - `feat(sdk): implement @trace decorator with SQLite storage`
  - `feat(dashboard): add waterfall timeline view`
  - `fix(sdk): handle JSON serialization of non-serializable outputs`
  - `docs: update README with quickstart`
- Always commit BEFORE starting a new feature (clean checkpoint)
- Push to `origin main` after each commit

---

## Design system (for dashboard + web)

```css
--bg:       #080b10   /* page background */
--bg-2:     #0d1117   /* card background */
--bg-3:     #131920   /* elevated surface */
--accent:   #00c2ff   /* primary cyan */
--green:    #00e5a0   /* success / tool spans */
--orange:   #ff9f40   /* warnings / redundant calls */
--red:      #ff4d6a   /* errors */
--purple:   #a78bfa   /* agent spans */

Fonts:
  Display:  DM Serif Display (headlines)
  Mono:     DM Mono (code, IDs, numbers)
  Body:     DM Sans (UI text)
```

---

## Wedge and positioning (keep this in mind for copy/README)

We are NOT "the first to share traces" — Langfuse and LangSmith both do that.
We are the **fastest, lowest-friction path** from broken agent to shareable trace:
- No account ever required (install, use, share — all anonymous)
- 60-second install vs 20+ minutes for competitors  
- Mandatory pre-share privacy review (auto-redact secrets before upload)
- Designed for indie devs, not enterprise teams

---

## Jonathan's working style

- Pastes full session-N prompts from Claude (claude.ai) into Claude Code
- Reads every diff before approving — never just says "yes" blindly
- Asks "why did you do this?" for anything non-obvious
- Git checkpoint before each major change
- Reports back to Claude (claude.ai) at end of each session with recap
- Buffer days built into schedule — don't try to fill them with extra features
- Currently learning: Python decorators, contextvars, SQLAlchemy 2.x, HTMX, Railway

---

## External resources

- GitHub: `https://github.com/glasspipe/glasspipe` (org: glasspipe)
- PRD v1.1: in `~/Desktop/glasspipe-private/` and on Google Drive → "GlassPipe" folder
- Landing page mockup: `packages/web/landing-mockup.html`
- Competitor references: Langfuse, LangSmith, Helicone, Arize Phoenix
