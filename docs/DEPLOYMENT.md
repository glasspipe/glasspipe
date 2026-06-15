# Deployment

GlassPipe uses one Vercel project and one Supabase Free Postgres database:

- Vercel serves the static marketing site from `packages/web`.
- Vercel runs the existing Flask share API through `api/index.py`.
- Supabase stores newly shared traces in Postgres.

## Vercel project settings

Connect the `glasspipe/glasspipe` repository and use these settings:

| Setting | Value |
|---|---|
| Root Directory | repository root (`.`) |
| Framework Preset | Other |
| Build Command | leave empty |
| Output Directory | leave empty |
| Install Command | leave empty |

Do not override Build Command or Output Directory in the Vercel dashboard. The
committed `vercel.json` publishes `packages/web` and routes the hosted API and
viewer paths to the Flask function.

Add both `glasspipe.dev` and `www.glasspipe.dev` under Vercel Project Settings
> Domains. The apex domain should be the production domain.

## Supabase database

Create a Supabase Free project and copy its pooled Postgres connection string.
Use the transaction pooler connection string for Vercel's serverless functions.
No old Railway data needs to be migrated.

Set these variables for Production, Preview, and Development in Vercel Project
Settings > Environment Variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase transaction pooler connection string |
| `GLASSPIPE_BASE_URL` | `https://glasspipe.dev` |

Optional variables:

| Variable | Default |
|---|---|
| `GLASSPIPE_MAX_PAYLOAD_MB` | `5` |
| `GLASSPIPE_TRACE_TTL_DAYS` | `30` |

Redeploy after adding or changing environment variables.

## Routes

The single Vercel project serves:

- `GET /` and marketing assets from `packages/web`
- `GET /health` from Flask
- `POST /v1/share` from Flask
- `GET /v1/trace/<id>` from Flask
- `GET /t/<id>` and `GET /t/<id>/embed` from Flask
- `GET /static/*` for the trace viewer's assets

The first successful `POST /v1/share` creates the `shared_traces` table in the
fresh Supabase database. The published SDK already posts to
`https://glasspipe.dev/v1/share`; local development can override that endpoint
with `GLASSPIPE_SHARE_API`.

## Verification

```bash
curl -i https://glasspipe.dev/
curl -i https://glasspipe.dev/health
curl -i -X POST https://glasspipe.dev/v1/share \
  -H 'content-type: application/json' \
  --data-binary @packages/web/demo_trace.json
```

The share request should return `201` with a `url`. Open that URL and confirm
the public trace viewer loads.
