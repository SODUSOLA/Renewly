# Renewly

Track the documents that expire in your life (driver's license, car insurance,
vehicle registration, permits, anything custom) and get an email **before** they
lapse.

- Reminders go out at configurable offsets (default 90, 30, 14, 7 and 1 days before expiry), at 8am **in each user's own timezone**.
- Each reminder is sent **exactly once**, even if the job runs many times or two workers collide.
- A dashboard groups documents as **expired / expiring soon / valid** with days left.
- "Mark as renewed" moves the expiry forward, keeps a renewal history and re-arms the reminders.

| Part | Folder | Stack |
|---|---|---|
| API and reminder engine | [`backend/`](backend) | FastAPI, PostgreSQL, Celery, Redis, Resend |
| Web app | [`frontend/`](frontend) | React, TypeScript, Vite |

## Run it locally (about 10 minutes)

You need Python 3.11 or newer (developed on 3.14), Node 22 and Docker.

```bash
# 1. Start PostgreSQL and Redis
docker compose up -d

# 2. Backend: install, configure, create the tables, start the API
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then set SECRET_KEY to a random string:
                              #   python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head
uvicorn app.main:app --reload
```

In a second terminal, the web app:

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm run dev
```

Open <http://localhost:5173>, create an account, and add a document. The API's own
interactive docs are at <http://localhost:8000/docs>.

### Send reminders

Reminders are sent by a Celery worker with a scheduler (Beat) that runs the job
every hour. In another terminal:

```bash
cd backend && source .venv/bin/activate
celery -A app.core.celery_app worker --beat --loglevel=info
```

With no `RESEND_API_KEY` set, emails are **printed to the log instead of sent**,
which is the right behaviour for development. To send real email, see
[docs/deployment.md](docs/deployment.md#5-make-email-actually-reach-people). To run the
job right now instead of waiting for the hour:

```bash
python -c "from app.modules.reminders.tasks import send_due_reminders; print(send_due_reminders())"
```

## Tests

```bash
cd backend  && pytest --cov     # needs `docker compose up -d`; fails below 95% coverage
cd frontend && npm test         # plus: npm run typecheck
```

Backend tests run against a separate `expiry_tracker_test` database on the same
PostgreSQL server (created automatically; your development data is never touched).

## Configuration

Backend settings come from environment variables or `backend/.env`; see
[`backend/.env.example`](backend/.env.example) for the annotated list. The ones you
will actually touch:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `SECRET_KEY` | required | Signs login tokens (32+ characters in production) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and rate-limit counters |
| `CORS_ORIGINS` | `http://localhost:5173` | Web app origin(s) allowed to call the API |
| `FRONTEND_URL` | empty | Used for the link in password-reset emails |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime; an `HttpOnly` refresh cookie (30 days sliding, 90 max) renews it silently |
| `COOKIE_SAMESITE` | `lax` | Needs the web app and API on one site; see [deployment.md](docs/deployment.md#sessions-and-cookies) |
| `APP_ENV` | `development` | `production` enforces a strong secret and a Resend key |
| `RESEND_API_KEY` / `EMAIL_FROM` | empty | Empty key means "log emails, do not send" |

The frontend has one setting, `VITE_API_URL` (the API's address), which is baked in at build time.

## Project layout

```text
backend/
  app/
    main.py               FastAPI app: routers, CORS, middleware, health checks
    core/                 config, database, security, rate limiting, logging, errors, Celery
    common/               enums and date helpers
    modules/              auth, vehicles, documents, dashboard, reminders, notifications
                          (each: models.py, schemas.py, service.py, router.py)
  alembic/                database migrations
  tests/                  pytest suite
frontend/
  src/
    api/                  fetch client, types, React Query hooks
    auth/                 sign-in state and route protection
    pages/                one file per screen
    components/           shared UI (forms, modal, badges...)
    lib/                  small pure helpers (dates, offsets)
docs/                     api.md, architecture.md, deployment.md
.github/workflows/        CI: backend, frontend and both Docker images
```

## More documentation

- [docs/api.md](docs/api.md): every endpoint with examples, errors and rate limits
- [docs/architecture.md](docs/architecture.md): how it fits together and why
- [docs/deployment.md](docs/deployment.md): deploying to Railway, release checklist, operations

## Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` on port 5432 or 6379 | Start the services: `docker compose up -d` (Docker Desktop must be running) |
| `ValidationError ... secret_key` on backend start | Create `backend/.env` (`cp .env.example .env`) and set `SECRET_KEY` |
| The web app shows "Can't reach the server" | Is the API running on the address in `VITE_API_URL`? In the browser console, a CORS error means the web app's address isn't in `CORS_ORIGINS` |
| `429 Too many requests` | A rate limit was hit; wait for `Retry-After` seconds. Limits are listed in [docs/api.md](docs/api.md) |
| No emails arrive | Without `RESEND_API_KEY` emails are only logged. With a key, check the worker log for `Resend rejected the email` (usually an unverified sender domain) |
