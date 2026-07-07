# Deployment

GlassPipe has two independently deployable services:

- `packages/web`: the static marketing site
- `packages/api`: the Flask share API and public trace viewer

## Marketing site on Vercel

The root `vercel.json` publishes `packages/web` directly. Use these Vercel
project settings:

| Setting | Value |
|---|---|
| Repository | `glasspipe/glasspipe` |
| Root Directory | repository root (`.`) |
| Framework Preset | Other |
| Build Command | leave empty |
| Output Directory | `packages/web` |
| Install Command | leave empty |

The committed `vercel.json` supplies the Build Command and Output Directory, so
the dashboard values should not override them. After the preview deployment
shows the landing page, add `glasspipe.dev` and `www.glasspipe.dev` under
Vercel Project Settings > Domains and apply the DNS records Vercel provides.

No environment variables are required for the static marketing site.

## Hosted share API

**Current production state (verified 2026-07-07):** the API is live and served
by the Vercel project **`glasspipe`** (`glasspipe.vercel.app`) — the same
project also serves the landing page, with `glasspipe.dev` as its domain.
`/health`, `POST /v1/share`, `GET /v1/trace/<id>`, and `GET /t/<id>` all
answer there. That deployment was made from a configuration that is **not**
checked into this repo (the committed `vercel.json` is static-only and the
repo contains no Vercel serverless adapter for the Flask app), and the Vercel
project does not auto-deploy from GitHub. Practical consequences:

- API env-var changes (e.g. `GLASSPIPE_PINNED_TRACES`) are made in the Vercel
  dashboard for the `glasspipe` project, followed by a redeploy of that
  project.
- Do not point the Vercel project at this repo's `main` without first adding
  the serverless/rewrite configuration it needs, or the API routes go dead.

The sections below describe running the API on any long-running Python host
(the original plan; still valid if it ever moves off Vercel functions). It has
Railway-era deployment files in `packages/api`, but it can run on any host
that supports Gunicorn and Postgres. Set the service root to `packages/api`
and start it with:

```bash
gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT
```

Required API environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Persistent Postgres connection string |
| `GLASSPIPE_BASE_URL` | `https://glasspipe.dev` when the routes below are proxied through the main domain |

Optional API environment variables:

| Variable | Default |
|---|---|
| `GLASSPIPE_MAX_PAYLOAD_MB` | `5` |
| `GLASSPIPE_TRACE_TTL_DAYS` | `30` |
| `GLASSPIPE_PINNED_TRACES` | empty — comma-separated trace ids exempt from expiry |
| `PORT` | supplied by the hosting platform |

Set `GLASSPIPE_PINNED_TRACES=7sq3QX,TyvF6u` so the demo traces linked from the
landing page and README never expire (they are re-shared 2026-07-07; without
pinning they die every TTL window and the marketing site 404s).

After the API has a healthy HTTPS URL, add external rewrites to `vercel.json`
so the public domain continues to match the SDK's default share URL:

```json
"rewrites": [
  {
    "source": "/v1/:path*",
    "destination": "https://YOUR-API-HOST/v1/:path*"
  },
  {
    "source": "/t/:path*",
    "destination": "https://YOUR-API-HOST/t/:path*"
  },
  {
    "source": "/static/:path*",
    "destination": "https://YOUR-API-HOST/static/:path*"
  }
]
```

Verify the API host's `/health` route before adding the rewrites. The published
SDK posts to `https://glasspipe.dev/v1/share` by default; local development can
override that endpoint with `GLASSPIPE_SHARE_API`.
