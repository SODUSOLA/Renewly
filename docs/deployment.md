# Deploying to Railway

The app runs as **three processes from one Docker image**, plus Postgres and Redis:

| Service | Start command | Config file | Notes |
|---|---|---|---|
| `api` | uvicorn (image default) | `railway.json` | Runs `alembic upgrade head` before each deploy; health-checked on `/health/ready` |
| `worker` | `celery … worker` | `railway.worker.json` | Executes the reminder job |
| `beat` | `celery … beat` | `railway.beat.json` | The scheduler. **Exactly one replica, ever**, or reminders are enqueued twice (they would still be sent once, but do not rely on that) |
| Postgres, Redis | Railway plugins | | |

CI is in `.github/workflows/ci.yml`: every push and pull request runs the
migrations from scratch, checks they match the models, runs the tests (95% coverage
minimum) and confirms the Docker image builds and starts.

> The Dockerfile, the three processes and the migration step were verified
> locally with Docker (see "What was verified" below). The Railway configuration
> itself could not be tried without your account, so follow the checklist and
> check the first deploy's logs.

## One-time setup

### 1. Put the project on GitHub
Create a repository, push this project, and make sure the `CI` workflow goes green.
(`.env` is git-ignored; never commit it.)

### 2. Create the Railway project
1. New Project → **Deploy from GitHub repo** → pick the repository. This creates the `api` service.
2. **+ New → Database → PostgreSQL**, then **+ New → Database → Redis**.
3. **+ New → GitHub Repo** (same repo) twice more and name the services `worker` and `beat`.

### 3. Point each service at its config file
Service → **Settings → Config-as-code → Config file path**:

- `api` → `/railway.json`
- `worker` → `/railway.worker.json`
- `beat` → `/railway.beat.json`

### 4. Set variables
On **each of the three services** (Railway's reference syntax pulls values from the plugins):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (the app converts `postgresql://` to the psycopg driver form itself) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `SECRET_KEY` | A random 48+ character string. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. **Use the same value on all three services** |
| `APP_ENV` | `production` (enforces a strong secret and a Resend key) |
| `RESEND_API_KEY` | From resend.com (see step 5) |
| `EMAIL_FROM` | An address on your verified domain, e.g. `Expiry Tracker <reminders@yourdomain.com>` |
| `LOG_FORMAT` | `json` |
| `SENTRY_DSN` | Optional: your Sentry project's DSN |

Defaults for everything else are in `.env.example`.

### 5. Make email actually reach people
Resend only delivers to arbitrary recipients from a **verified domain**:

1. Resend → Domains → Add domain, then add the DNS records it shows (SPF and DKIM) at your DNS provider.
2. Wait until the domain shows "Verified", then set `EMAIL_FROM` to an address on it.

Without this, reminders either fail or land in spam. This is the main launch risk in the project plan.

### 6. Expose the API
`api` service → **Settings → Networking → Generate Domain** (or attach your own).
Open `https://<domain>/health/ready` and `/docs`.

## Release checklist (milestone M6)

- [ ] CI is green on `main`
- [ ] `https://<domain>/health/ready` returns `{"status":"ready"}`
- [ ] Register your own account through `/docs`
- [ ] Add a **real** document of yours with an expiry date and reminder offsets that make one due **today** (e.g. expiry in 7 days, offsets `[7]`)
- [ ] Wait for the next `:05` past the hour (and your local time to be ≥ 08:00); the email arrives
- [ ] The `worker` log shows `Reminder run finished: ReminderRunSummary(sent=1 …)`
- [ ] A second run the same day sends nothing (`skipped=1`)
- [ ] Trigger a test error and confirm it appears in Sentry (if configured)

To avoid waiting, once the worker is up run the job immediately from the `worker`
service's shell (Railway → service → ⋯ → Shell, or `railway run`):

```bash
celery -A app.core.celery_app call reminders.send_due_reminders
```

## Operations

**Deploys.** Merging to `main` triggers a deploy of all three services. In each
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
