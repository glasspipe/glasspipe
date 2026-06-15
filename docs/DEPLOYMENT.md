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

The Flask API needs a separate long-running deployment with persistent
Postgres. It is not deployed by the marketing-site Vercel project. Until it is
redeployed, these routes will not work:

- `POST /v1/share`
- `GET /v1/trace/<id>`
- `GET /t/<id>`
- `GET /t/<id>/embed`

The API currently has Railway deployment files in `packages/api`, but it can
run on any Python host that supports Gunicorn and Postgres. Set the service
root to `packages/api` and start it with:

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
| `PORT` | supplied by the hosting platform |

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
