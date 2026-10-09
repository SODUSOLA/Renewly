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
| `TRUSTED_PROXY_HOPS` | `1` on Railway (its edge proxy is the one hop in front of the API). **Required for correct rate limiting**, see [Client IPs](#client-ips-and-rate-limits) |
| `COOKIE_SAMESITE` | `lax` when the web app and API share a site (see [Sessions and cookies](#sessions-and-cookies)) |
| `COOKIE_PATH` | Leave at `/auth` unless the API is served under a path prefix |
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

### Hosting the web app on Vercel

`frontend/vercel.json` does two things, and **both are required**:

1. **Single-page-app routing.** Any address except `/api/*` serves `index.html`, so opening or reloading `/login`, `/documents/…` etc. works. Without this, Vercel answers `404` for everything but `/`.
2. **An `/api` proxy.** `/api/*` is forwarded to the Railway API (the `destination` host in that file; edit it if your API address changes). To the browser the app and API are one origin, so the login cookie is first-party and works in Safari and Firefox without a custom domain.

Vercel project settings:

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework Preset | Vite (build `npm run build`, output `dist`: the defaults) |
| Environment variable `VITE_API_URL` | `/api` (**build-time**: after setting or changing it, redeploy; without it the app calls `http://localhost:8000` from every visitor's own machine) |

Railway `api` service variables for this setup:

| Variable | Value |
|---|---|
| `CORS_ORIGINS` | `https://<your-project>.vercel.app` (exact origin; also what `/auth/refresh` and `/auth/logout` accept as `Origin`) |
| `FRONTEND_URL` | the same URL (reset and digest emails link here) |
| `COOKIE_PATH` | `/api/auth` (the path the **browser** sees, because the cookie is set for `/api/auth/*`) |
| `COOKIE_SAMESITE` | leave at the default `lax` |
| `TRUSTED_PROXY_HOPS` | start with `2` (Vercel's proxy, then Railway's edge), then verify below |

Verify after redeploying both sides:

- `https://<app>.vercel.app/login` loads (not 404) and `https://<app>.vercel.app/api/health` returns `{"status":"ok"}`: that second one proves the proxy reaches the API.
- Sign in, reload the page: you stay signed in.
- **Client IP:** in the Railway `api` logs, the request line's `client_ip` must be your own public IP. If it shows a Vercel or Railway address the value is too low; if it shows an address you did not send it is too high (see below). Do not leave it at a value you have not checked.

Preview deployments get different URLs that are not in `CORS_ORIGINS`, so sign-in will not work on them unless you add them.

### Client IPs and rate limits

Per-IP rate limits (sign-up, login, password reset, refresh) need the caller's real address.
Behind a load balancer the connecting address is the balancer's, so the real one is read
from the `X-Forwarded-For` header, which every proxy appends to. Callers can put anything
they like at the *start* of that header, so the app never reads the first value. It counts
`TRUSTED_PROXY_HOPS` entries from the **right**, which are the ones your own proxies wrote.

- Set `TRUSTED_PROXY_HOPS=1` on the `api` service (Railway's edge is one proxy).
- If you later put another proxy in front (a CDN, or the web app's nginx forwarding `/api`), add one.
- **Do not set it higher than the real number of proxies**: the extra step would land on a value the caller controls, and spoofing works again.
- Left at `0` in production, every user appears to come from the proxy and all share one per-IP bucket (the app logs a warning at start-up saying so). The per-email limits still apply.

To check it after deploying, open the `api` logs, make a request from your own device, and
compare the `client_ip` field on the request line with your public IP (search "what is my
IP"). Every request log line carries it. If it shows a Railway address instead, the value is
too low; if it shows something you did not send, it is too high.

The image starts uvicorn with `--no-proxy-headers` on purpose: uvicorn's own handling,
combined with a wildcard allow-list, believes the first forwarded value and is exactly the
spoofable behaviour this setting replaces.

### Sessions and cookies

Logins use a short-lived access token (15 minutes, in page memory) plus a refresh token in an
`HttpOnly` cookie that renews it silently; see [architecture.md](architecture.md#sessions).
That cookie has one hard requirement: **the web app and the API must be on the same
site.**

| Setup | Works? | Settings |
|---|---|---|
| **Your own domain, two subdomains**, e.g. `app.example.com` (web) and `api.example.com` (API) | Yes, in every browser. Recommended | `COOKIE_SAMESITE=lax` (default), `CORS_ORIGINS=https://app.example.com`, `FRONTEND_URL=https://app.example.com`, `VITE_API_URL=https://api.example.com` |
| Default Railway names (`*.up.railway.app`) for both | **Partly.** These are different sites, so the cookie is "third-party": Safari and Firefox block it, and users there are signed out on every page reload (their access token still works for 15 minutes after login). Chrome allows it | `COOKIE_SAMESITE=none` (the app then requires HTTPS cookies) |
| Web app forwards `/api/*` to the API (same origin) | Yes, in every browser, **no custom domain needed** | `VITE_API_URL=/api`, `COOKIE_PATH=/api/auth`, `CORS_ORIGINS` = the web app's URL. Built in for Vercel (`frontend/vercel.json`); see [Hosting the web app on Vercel](#hosting-the-web-app-on-vercel) |

So for real users, attach a custom domain to both services (Railway: service →
Settings → Networking → Custom Domain, then add the CNAME it shows at your DNS provider)
before you rely on sessions. You are already adding DNS records for Resend, so this is the
same place.

`CORS_ORIGINS` must be the web app's exact origin (`https://…`, no path, no trailing
slash): it controls both which pages may call the API and which `Origin` values
`/auth/refresh` and `/auth/logout` accept.

**Scheduled jobs.** The `beat` service runs: reminders (hourly, minute 5), the six-monthly spending report
(hourly, minute 20; does nothing outside the first week of January and July), and a daily purge of expired
refresh tokens. All run on the `worker`. Check the worker log for lines such as `Six-monthly report run finished`.

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
