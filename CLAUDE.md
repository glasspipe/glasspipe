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

## Current state (updated 2026-07-07)

- **Version:** 0.2.0 in repo (0.1.9 is the latest published to PyPI — release pending)
- **Test suite:** 64/64 green (includes Flask test-client dashboard tests)
- **What works:** full stack live — SDK, local dashboard (HTMX partial rendering,
  version filter chips, run compare, anomaly watch, live cost ticker, trace
  replay), share flow with delete tokens, public viewer with view counts,
  landing page, PyPI package, `glasspipe demo` seeder, CI test workflow
- **Live demo traces:** glasspipe.dev/t/7sq3QX and glasspipe.dev/t/TyvF6u
  (re-shared 2026-07-07; set GLASSPIPE_PINNED_TRACES=7sq3QX,TyvF6u on the API
  deployment or they expire after 30 days and the landing page 404s again)
- **Hosting (verified 2026-07-07):** ONE Vercel project — `glasspipe.vercel.app`
  / glasspipe.dev — serves BOTH the landing page (packages/web) and the Flask
  share API (as a serverless function via api/index.py), with Postgres on
  Supabase. The Vercel project IS git-connected to origin/main, so pushes to
  main deploy production. The config lives in the repo: vercel.json (functions
  + rewrites), api/index.py, root requirements.txt — these arrived on
  origin/main via commits 87340ba..f5e38ca (made outside this machine; local
  main had diverged until merged 2026-07-07). Env vars (DATABASE_URL,
  GLASSPIPE_BASE_URL, GLASSPIPE_PINNED_TRACES) are set in the Vercel
  dashboard; redeploy after changing them. See docs/DEPLOYMENT.md.
- **Machine note:** this repo lives in iCloud-synced ~/Desktop, and iCloud
  re-applies the macOS `hidden` flag to new .pth files, which Python 3.13+
  skips — that used to break `pip install -e` silently. FIXED 2026-07-07: the
  real venv is `.venv.nosync/` (iCloud ignores *.nosync) with `.venv` as a
  symlink to it, holding a normal editable install. If the venv is ever
  rebuilt, recreate it as `.venv.nosync` + symlink.
- **Next session:** demo video + launch prep

---

## Repository layout

```
glasspipe/                          ← repo root, ~/Desktop/glasspipe
├── CLAUDE.md                       ← this file (AGENTS.md is its Codex twin — keep in sync)
├── .github/workflows/              ← tests.yml (pytest matrix) + publish.yml (PyPI)
├── .gitignore
├── LICENSE                         ← MIT, 2026 Jonathan
├── README.md                       ← keep in sync with packages/sdk/README.md (PyPI copy)
├── vercel.json                     ← landing page deploy (rewrites NOT committed — see docs/DEPLOYMENT.md)
├── .venv/                          ← shared virtualenv (never commit)
├── docs/
│   ├── DEPLOYMENT.md               ← Vercel + share-API deployment runbook
│   └── dashboard.png               ← README screenshot
├── examples/                       ← hello, research, support, competitive intel,
│                                     live before/after pair (needs OPENAI_API_KEY)
└── packages/
    ├── sdk/                        ← the pip-installable library (version 0.2.0)
    │   ├── pyproject.toml          ← hatchling backend
    │   ├── tests/                  ← 64 tests incl. Flask test-client dashboard suite
    │   └── src/glasspipe/
    │       ├── __init__.py         ← exports: trace, span, redact, detect
    │       ├── trace.py            ← @trace decorator + span() context manager
    │       ├── storage.py          ← SQLAlchemy models + DB write functions
    │       ├── redact.py           ← secret detection + redaction (implemented)
    │       ├── share.py            ← share_run/upload_run → glasspipe.dev/v1/share
    │       ├── cli.py              ← click CLI: dashboard (--port), demo
    │       ├── _dashboard.py       ← THE local dashboard Flask app (port 3000)
    │       ├── _demo.py            ← `glasspipe demo` sample-trace seeder
    │       ├── _diff.py            ← run comparison engine
    │       ├── templates/          ← dashboard Jinja templates (incl. _runs_container.html partial)
    │       ├── static/             ← style.css, vendored htmx.min.js
    │       └── instruments/        ← auto-patch openai, anthropic
    ├── api/                        ← hosted Flask share service, port 5051
    │   ├── app.py                  ← share/view/delete endpoints, pinned demo traces
    │   └── requirements.txt
    └── web/                        ← static landing page (deployed to Vercel)
        ├── index.html
        └── landing-mockup.html     ← design reference, DO NOT modify
```

Note: there is no packages/dashboard — the dashboard ships inside the SDK
(`glasspipe/_dashboard.py`) so `pip install glasspipe` includes it.

---

## Tech stack (locked — do not change without asking)

| Layer | Choice | Notes |
|---|---|---|
| SDK language | Python 3.10+ | Jonathan has 3.14.3 locally |
| Build backend | hatchling | modern, src-layout native |
| Local DB | SQLite via SQLAlchemy 2.x | `~/.glasspipe/traces.db` |
| DB path override | `GLASSPIPE_DB_PATH` env var | full file path |
| Dashboard | Flask + HTMX (vendored) | NOT React; ships in SDK, port 3000 |
| Hosted API | Flask + Postgres | any gunicorn host; see docs/DEPLOYMENT.md |
| Deploy | Vercel (web) + gunicorn host (API) | landing at glasspipe.dev |
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
  agent_version   TEXT       -- nullable, @trace(version=) or GLASSPIPE_AGENT_VERSION
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
  payload         JSON       -- full run + spans, post-redaction
  created_at      DATETIME
  expires_at      DATETIME   -- created_at + 30 days (pinned ids exempt)
  delete_token    TEXT       -- secret for DELETE /v1/trace/<id>
  view_count      INTEGER    -- incremented on each public view
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

# install SDK in editable mode (works again — venv lives in .venv.nosync)
pip install -e "packages/sdk[dev]"

# run tests
pytest packages/sdk/tests/ -v

# seed sample traces, then run dashboard
glasspipe demo
glasspipe dashboard              # → localhost:3000 (or --port N)

# run API
python packages/api/app.py       # → localhost:5051

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
