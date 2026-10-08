# Expiry Tracker

Track the documents that expire in your life (driver's license, car insurance,
vehicle registration, permits, anything custom) and get an email **before** they
lapse. Built with FastAPI, PostgreSQL, Celery and Resend.

- Reminders go out at configurable offsets (default 90, 30, 14, 7 and 1 days before expiry), at 08:00 **in each user's own timezone**.
- Each reminder is sent **exactly once**, even if the job runs many times or two workers collide.
- A dashboard groups documents as **expired / expiring soon / valid** with days left.
- "Mark as renewed" moves the expiry forward, keeps a renewal history and re-arms the reminders.

## Run it in 10 minutes

You need Python 3.11 or newer (developed on 3.14) and Docker.

```bash
# 1. Install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configure (the defaults work for local development, except SECRET_KEY)
cp .env.example .env
# edit .env and set SECRET_KEY to a random string:
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. Start PostgreSQL and Redis, then create the tables
docker compose up -d
alembic upgrade head

# 4. Start the API
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the interactive API explorer.

### Try it

```bash
# Create an account
curl -s localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"correct-horse","full_name":"You"}'

# Log in and keep the token
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"correct-horse"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Track a document (use a real future date)
curl -s localhost:8000/documents -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"type":"insurance","title":"Car insurance","expiry_date":"2027-03-01"}'

# See the dashboard
curl -s localhost:8000/dashboard -H "authorization: Bearer $TOKEN"
```

### Send reminders

Reminders are sent by a Celery worker with a scheduler (Beat) that runs the job
every hour. In another terminal:

```bash
celery -A app.core.celery_app worker --beat --loglevel=info
```

With no `RESEND_API_KEY` set, emails are **printed to the log instead of sent**,
which is the right behaviour for development. To send real email:

1. Create an API key at <https://resend.com>.
2. Put it in `.env` as `RESEND_API_KEY`.
3. For first tests, keep `EMAIL_FROM=Expiry Tracker <onboarding@resend.dev>` (it only delivers to your own Resend account email). For real users, verify your domain in Resend (SPF/DKIM) and set `EMAIL_FROM` to an address on it.

To trigger the job right now instead of waiting for the hour:

```bash
python -c "from app.modules.reminders.tasks import send_due_reminders; print(send_due_reminders())"
```

## Configuration

All settings come from environment variables or `.env`. See [`.env.example`](.env.example) for the annotated list.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `SECRET_KEY` | required | Signs login tokens (32+ characters in production) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and rate-limit counters |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Login token lifetime |
| `DEFAULT_TIMEZONE` | `Africa/Lagos` | Timezone for users who do not pick one |
| `APP_ENV` | `development` | `production` enforces a strong secret and a Resend key |
| `RESEND_API_KEY` | empty | Empty means "log emails, do not send" |
| `EMAIL_FROM` | `Expiry Tracker <onboarding@resend.dev>` | Sender address |
| `LOG_FORMAT` / `LOG_LEVEL` | `text` / `INFO` | Use `json` in production |
| `RATE_LIMIT_BACKEND` | `redis` | `memory` for a single process |
| `SENTRY_DSN` | empty | Empty disables error tracking |

## Tests

```bash
pytest --cov
```

Tests run against a separate `expiry_tracker_test` database on the same
PostgreSQL server (created automatically; your development data is never
touched) and need the `docker compose` services running. The suite fails if
coverage drops below 95%.

## Project layout

```text
app/
  main.py                 FastAPI app: routers, middleware, health checks
  core/                   config, database, security, rate limiting, logging, errors, Celery
  common/                 enums and date helpers shared across modules
  modules/
    auth/                 register, login, /me, password reset
    vehicles/             vehicle CRUD
    documents/            document CRUD, soft delete, renewal
    dashboard/            documents grouped by status
    reminders/            the reminder engine and its Celery task
    notifications/        email sending (Resend) and email templates
alembic/                  database migrations
Dockerfile, railway*.json one image, three processes (see docs/deployment.md)
.github/workflows/        CI: migrations, tests, Docker build
tests/                    pytest suite
docs/                     architecture.md, api.md
```

Each module follows the same shape: `models.py` (tables) → `schemas.py`
(request/response shapes) → `service.py` (business rules) → `router.py` (HTTP).

## More documentation

- [docs/api.md](docs/api.md): every endpoint with examples, errors and rate limits
- [docs/architecture.md](docs/architecture.md): how it fits together and why
- [docs/deployment.md](docs/deployment.md): deploying to Railway, release checklist, operations

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on port 5432 or 6379 | Start the services: `docker compose up -d` (Docker Desktop must be running) |
| `ValidationError ... secret_key` on startup | Create `.env` (`cp .env.example .env`) and set `SECRET_KEY` |
| `429 Too many requests` | A rate limit was hit; wait for `Retry-After` seconds. Limits are listed in [docs/api.md](docs/api.md) |
| No emails arrive | Without `RESEND_API_KEY` emails are only logged. With a key, check the worker log for `Resend rejected the email` (usually an unverified sender domain) |
| Tests fail to connect | The test database is created on the same server as `DATABASE_URL`; make sure PostgreSQL is up |
