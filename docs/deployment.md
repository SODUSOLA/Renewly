# Deploying to Railway

The repository holds two apps, `backend/` and `frontend/`. On Railway they become **four services** plus Postgres and Redis. The three backend services share one Docker image:

| Service | Start command | Config file | Notes |
|---|---|---|---|
| `api` | uvicorn (image default) | `backend/railway.json` | Runs `alembic upgrade head` before each deploy; health-checked on `/health/ready` |
| `worker` | `celery … worker` | `backend/railway.worker.json` | Executes the reminder job |
| `beat` | `celery … beat` | `backend/railway.beat.json` | The scheduler. **Exactly one replica, ever**, or reminders are enqueued twice (they would still be sent once, but do not rely on that) |
| `web` | nginx serving the built React app | `frontend/railway.json` | Static site; the API address is baked in at build time |
| Postgres, Redis | Railway plugins | | |

CI is in `.github/workflows/ci.yml`: every push and pull request runs the backend
migrations from scratch, checks they match the models, runs the backend tests (95%
coverage minimum), type-checks, tests and builds the frontend, and confirms both Docker
images build.

> The Dockerfile, the three processes and the migration step were verified
> locally with Docker (see "What was verified" below). The Railway configuration
> itself could not be tried without your account, so follow the checklist and
> check the first deploy's logs.

## One-time setup

### 1. Put the project on GitHub
Create a repository, push this project, and make sure the `CI` workflow goes green.
(`.env` is git-ignored; never commit it.)

### 2. Create the Railway project
1. New Project → **Deploy from GitHub repo** → pick the repository. This creates the first service; call it `api`.
2. **+ New → Database → PostgreSQL**, then **+ New → Database → Redis**.
3. **+ New → GitHub Repo** (same repo) three more times and name the services `worker`, `beat` and `web`.

### 3. Point each service at its folder and config file
Because everything lives in one repository, each service needs to know which folder is
its own. Service → **Settings → Source → Root Directory**, and **Settings → Config-as-code
→ Config file path**:

| Service | Root Directory | Config file path |
|---|---|---|
| `api` | `/backend` | `/backend/railway.json` |
| `worker` | `/backend` | `/backend/railway.worker.json` |
| `beat` | `/backend` | `/backend/railway.beat.json` |
| `web` | `/frontend` | `/frontend/railway.json` |

> If a service fails to find its config or Dockerfile, check the two fields above first.
> Whether the config path is read relative to the repository root or to the Root Directory
> is the one thing to confirm on the first deploy: the build log shows which Dockerfile it used.
> As a fallback you can also set the **Pre-deploy Command** (`alembic upgrade head`),
> **Start Command** and **Healthcheck Path** by hand in each service's settings.

### 4. Set variables
**`api`, `worker` and `beat`** (Railway's reference syntax pulls values from the plugins):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (the app converts `postgresql://` to the psycopg driver form itself) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `SECRET_KEY` | A random 48+ character string. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. **Use the same value on all three services** |
| `APP_ENV` | `production` (enforces a strong secret and a Resend key) |
| `RESEND_API_KEY` | From resend.com (see step 5) |
| `EMAIL_FROM` | An address on your verified domain, e.g. `Renewly <reminders@yourdomain.com>` |
| `LOG_FORMAT` | `json` |
| `CORS_ORIGINS` | The web app's public URL, e.g. `https://renewly-web.up.railway.app` (**`api` only matters, but set it everywhere for consistency**) |
| `FRONTEND_URL` | The same web app URL; password-reset emails link to `<FRONTEND_URL>/reset-password` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | See [Sessions](#sessions) |
| `SENTRY_DSN` | Optional: your Sentry project's DSN |

**`web`:**

| Variable | Value |
|---|---|
| `VITE_API_URL` | The API's public URL, e.g. `https://renewly-production-77ea.up.railway.app` (no trailing slash) |

`VITE_API_URL` is compiled into the JavaScript, so **changing it requires a redeploy
(rebuild) of `web`**. Likewise the API only accepts browser calls from the origin listed in
`CORS_ORIGINS`: the exact address, with `https://` and no path.

Defaults for everything else are in `backend/.env.example`.

### 5. Make email actually reach people
Resend only delivers to arbitrary recipients from a **verified domain**:

1. Resend → Domains → Add domain, then add the DNS records it shows (SPF and DKIM) at your DNS provider.
2. Wait until the domain shows "Verified", then set `EMAIL_FROM` to an address on it.

Without this, reminders either fail or land in spam. This is the main launch risk in the project plan.

### 6. Expose the API and the web app
`api` and `web` → **Settings → Networking → Generate Domain** (or attach your own). `worker` and `beat` stay private.
Open `https://<api-domain>/health/ready`, then `https://<web-domain>` and sign up.

Order matters once: generate both domains, then fill in `CORS_ORIGINS`/`FRONTEND_URL` (on the backend) and `VITE_API_URL` (on `web`) with them and redeploy.

## Release checklist (milestone M6)

- [ ] CI is green on `main`
- [ ] `https://<domain>/health/ready` returns `{"status":"ready"}`
- [ ] Open the web app and register your own account
- [ ] Add a **real** document of yours with an expiry date and reminder offsets that make one due **today** (e.g. expiry in 7 days, offsets `[7]`)
- [ ] Wait for the next `:05` past the hour (and your local time to be ≥ 08:00); the email arrives
- [ ] The `worker` log shows `Reminder run finished: ReminderRunSummary(sent=1 …)`
- [ ] A second run the same day sends nothing (`skipped=1`)
- [ ] Trigger a test error and confirm it appears in Sentry (if configured)

To avoid waiting, once the worker is up run the job immediately from the `worker`
service's shell (Railway CLI: `railway ssh`, with the `worker` service selected):

```bash
celery -A app.core.celery_app call reminders.send_due_reminders
```

## Operations

**Deploys.** Merging to `main` triggers a deploy of all four services. In each
service's Settings enable **Wait for CI** so a red build never ships. The `api` runs
migrations first (`preDeployCommand`) and only replaces the old version once
`/health/ready` passes.

**Migrations.** Write them with `alembic revision --autogenerate -m "…"`, read the
generated file, commit it. Keep them backwards-compatible with the previous app
version (add columns as nullable, drop things in a later release), because the old
API keeps serving until the new one is healthy.

**Rollback.** Railway → service → Deployments → redeploy a previous build. If the
bad release included a migration, roll the schema back first with
`alembic downgrade -1` from a one-off shell.

**Backups.** Turn on Postgres backups for the database service in Railway and test
a restore once. The data (documents, history) is the product.

### Sessions

Access tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default **30**) and there is no
refresh token yet, so by default a user is signed out every 30 minutes (the web app handles
this by returning to the sign-in page with "Your session ended"). For a reminders app that
people open occasionally, set it to something like `10080` (7 days). The trade-off is that a
stolen token (the web app keeps it in `localStorage`) stays valid for that long. The
proper fix is short-lived tokens plus a refresh token in an `HttpOnly` cookie; it is the
first item on the v2 list.

**Logs.** JSON, one object per line, each with a `request_id` that is also returned
to the client in the `X-Request-ID` header and in error bodies. Search by it to follow
one request.

**Scaling.** The API is stateless: add replicas freely (rate limits are in Redis).
Add worker replicas only if a run takes long; the claim step keeps them from
double-sending. Never add `beat` replicas.

## What was verified locally

With the real Docker image against Postgres and Redis (the same ones used for development):

- The image builds (379MB, non-root user, timezone database present).
- `alembic upgrade head` creates the schema from a `postgresql://`-style URL, and `alembic check` reports no drift.
- The API starts, `/health/ready` is OK, a request succeeds and logs one JSON line, and the container healthcheck reports `healthy`.
- A worker consumes a `reminders.send_due_reminders` task from Redis and completes it; `beat` starts with the hourly schedule.

Not verified: the Railway-side configuration, Resend delivery to a real inbox, and Sentry ingestion. Those need your accounts, hence the checklist above.
