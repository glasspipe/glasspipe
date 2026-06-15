# Vercel + Supabase Share API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the existing Flask share API and public trace viewer from `glasspipe.dev` on Vercel, backed by a fresh Supabase Free Postgres database.

**Architecture:** Vercel continues publishing `packages/web` as the static landing page. A thin `api/index.py` Vercel Function imports the unchanged Flask application, while rewrites send only API/viewer routes to Flask. Supabase provides `DATABASE_URL`; Vercel provides the public domain and runtime.

**Tech Stack:** Vercel static hosting and Python Functions, Flask, SQLAlchemy, Supabase Postgres, pytest

---

### Task 1: Add a Vercel Flask entrypoint

**Files:**
- Create: `api/index.py`
- Create: `requirements.txt`
- Create: `packages/api/tests/test_vercel_entrypoint.py`

- [ ] Write a test that imports `api.index.app`, requests `/health`, and confirms the existing Flask app responds.
- [ ] Run the test and verify it fails because `api.index` does not exist.
- [ ] Add the thin Vercel entrypoint and root Python requirements file.
- [ ] Run the test and verify it passes.

### Task 2: Route hosted API and viewer traffic

**Files:**
- Modify: `vercel.json`
- Create: `packages/api/tests/test_vercel_config.py`

- [ ] Write tests asserting the landing page remains the static output and `/v1/*`, `/t/*`, and `/static/*` rewrite to the Flask function.
- [ ] Run the tests and verify they fail against the static-only configuration.
- [ ] Add the minimal Vercel rewrites and function file inclusion configuration.
- [ ] Run the tests and verify they pass.

### Task 3: Document the production setup

**Files:**
- Modify: `docs/DEPLOYMENT.md`

- [ ] Replace the separate-host/Railway guidance with the approved Vercel + Supabase Free setup.
- [ ] Document required Vercel variables: `DATABASE_URL` and `GLASSPIPE_BASE_URL=https://glasspipe.dev`.
- [ ] Document the exact Vercel project settings and end-to-end verification commands.

### Task 4: Deploy and verify

- [ ] Run API deployment tests and the full SDK test suite.
- [ ] Commit and push the deployment changes to `main`.
- [ ] Create a Supabase Free project and set its pooled Postgres URL as Vercel `DATABASE_URL`.
- [ ] Set `GLASSPIPE_BASE_URL=https://glasspipe.dev` in Vercel and redeploy.
- [ ] Verify `/`, `/health`, `POST /v1/share`, `/v1/trace/<id>`, and `/t/<id>` on the production domain.
