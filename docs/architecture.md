# Architecture

## The big picture

```text
                 ┌──────────────────────────────┐
  HTTP client ──▶│  FastAPI app (uvicorn)       │──┐
                 │  routers → services → models │  │
                 └──────────────┬───────────────┘  │ rate-limit
                                │ SQLAlchemy       │ counters
                                ▼                  ▼
                        ┌─────────────┐      ┌───────────┐
                        │ PostgreSQL  │      │   Redis   │◀── Celery broker
                        └─────────────┘      └───────────┘
                                ▲                  │
                 ┌──────────────┴───────────────┐  │
                 │ Celery worker + Beat (hourly)│◀─┘
                 │ reminders.send_due_reminders │───▶ Resend (email API)
                 └──────────────────────────────┘
```

Two processes share one codebase and one database: the **API** (request/response)
and the **worker** (the scheduled reminder job). Redis carries the Celery queue
and the rate-limit counters. Nothing else is stateful.

## Layers

Every feature lives in `app/modules/<name>/` and is split the same way, so you
always know where to look:

| File | Responsibility | Must not |
|---|---|---|
| `models.py` | Table definitions (SQLAlchemy) | contain business rules |
| `schemas.py` | Shape and basic validation of requests/responses (Pydantic) | touch the database |
| `service.py` | **The business rules.** Takes a session and a user, returns objects or raises a domain error | know about HTTP |
| `router.py` | HTTP only: parse the request, call the service, translate domain errors to status codes | contain rules |

Services raise plain exceptions (`VehicleNotFound`, `DocumentInvalid`...); routers
map them to `404`, `422`... This keeps the rules testable without HTTP and lets the
Celery worker reuse them.

`app/core/` holds cross-cutting infrastructure (config, DB session, security,
rate limiting, logging, error shape, Celery app). `app/common/` holds small shared
things (enums, date helpers).

## Data model

```text
users 1───* vehicles
  │            │ 0..1
  │            ▼
  └───* documents 1───* renewal_history
            │
            └───* reminder_log          users 1───* password_reset_tokens
```

| Table | Notes |
|---|---|
| `users` | Lowercased unique email, argon2 password hash, IANA `timezone`, `is_active` |
| `vehicles` | Unique `(user_id, plate_number)`; deleting a vehicle sets its documents' `vehicle_id` to NULL |
| `documents` | `expiry_date`, `reminder_offsets integer[]`, `deleted_at` for soft delete. CHECK constraints: expiry ≥ issue, custom type needs a label, offsets ≥ 0 |
| `renewal_history` | One row per "mark as renewed": previous and new expiry, date, optional cost |
| `reminder_log` | One row per reminder attempt; **unique** `(document_id, offset_days, expiry_date, channel)` is the dedup key |
| `password_reset_tokens` | SHA-256 hash of the emailed token, expiry, `used_at` |

Primary keys are UUIDs. Constraint names follow a fixed convention
(`app/core/base.py`) so migrations are stable. Enums are stored as `VARCHAR`, not
native Postgres enums, so adding a value (say `sms`) needs no `ALTER TYPE`.

## How reminders work

This is the heart of the product, so it is built to be boring and safe.

1. **Schedule.** Celery Beat enqueues `reminders.send_due_reminders` at minute 5 of every hour.
2. **Find what is due.** For each live document of an active user: take the owner's local time. If it is before 08:00, skip. Otherwise `days_left = expiry_date − local_today`; the document is due if `days_left` is one of its `reminder_offsets`.
3. **Claim.** One atomic `INSERT … ON CONFLICT DO UPDATE` into `reminder_log` as `pending`. The unique key means only one worker wins. The conflict branch only takes over rows that are `failed`, or `pending` for over 15 minutes (a crashed worker). A `sent` row is never taken.
4. **Send** through Resend with an `Idempotency-Key` of the log row id, so a retry after an ambiguous failure cannot deliver twice.
5. **Record** `sent`, or `failed` with the error. One failure never stops the rest of the run.

Consequences worth knowing:

- Running the job any number of times is harmless (this is what makes hourly runs safe).
- A failed send is retried on each later run that day while the reminder is still due; after that day the offset has passed.
- The dedup key contains `expiry_date`, so **renewing a document automatically re-arms** its reminders. No cleanup needed.
- If the system is down for a whole day, that day's reminders are missed rather than sent late in bulk. This is deliberate: it avoids a flood of stale emails after an outage.
- Documents created inside an offset window (e.g. 20 days before expiry with a 30-day offset) do not get the missed offset; they get the next one.

## Time handling

- Timestamps are stored in UTC (`timestamptz`).
- Expiry dates are plain dates, with no timezone.
- "Today" is computed **per user** from their IANA timezone (`app/common/dates.py`). The status shown on a document, the dashboard and the reminder job all use the same calculation, so they cannot disagree.
- The server's own date is never used for expiry maths.

## Security decisions

| Concern | Decision |
|---|---|
| Passwords | argon2; never stored or logged in plain text |
| Login | JWT bearer tokens (HS256, short-lived); identical error for wrong email and wrong password; dummy hash on unknown email to equalise timing |
| Password reset | Random token, only its SHA-256 stored, 1 hour expiry, single use, spends all siblings; the request endpoint answers identically for unknown emails |
| Data isolation | Every query filters by the current user; other people's rows return `404`, not `403` |
| Abuse | Redis rate limits per IP and per email (hashed in keys); fails open if Redis is down |
| Errors | Uniform JSON with a request id; internals and stack traces never reach clients |
| Secrets | Production refuses to start with a weak `SECRET_KEY`; a missing `RESEND_API_KEY` is a hard error there |
| Input | Pydantic validation at the edge plus database CHECK/UNIQUE constraints as the last line of defence |

## Observability

Each request gets an id (`X-Request-ID`), included on every log line and error
body. Set `LOG_FORMAT=json` for one JSON object per request with method, path,
status and duration. `/health` (liveness) and `/health/ready` (checks the
database) are for orchestrators and uptime monitors.

## Testing approach

- Real PostgreSQL, not mocks: the constraints, `ON CONFLICT` upsert and `ALL(array)` checks are exactly what must be proven. Tests use a separate `<db>_test` database; tables are truncated after each test.
- The email provider is faked at the boundary (`httpx.MockTransport` for Resend's wire format; an in-memory outbox for the reminder engine).
- The reminder engine takes `now` as a parameter, so timezone and "08:00" behaviour is tested with fixed instants rather than the clock.
- Rate limiting uses an in-memory backend in tests, plus one test against real Redis.

## Decisions log

| Decision | Why |
|---|---|
| Synchronous SQLAlchemy 2.0 + psycopg 3 | Celery tasks are synchronous; one DB style is simpler. Move to async only if load demands it |
| Status is derived, never stored | A stored status goes stale at midnight and needs a job to maintain; computing it is one subtraction |
| Soft delete for documents only | Documents carry history; vehicles are simple records and are hard-deleted |
| Hourly job + local 08:00 gate, not one daily run | Users in different timezones all get a morning email, and a transient failure is retried within the day |
| Per-document emails (no digest) | Simplest correct v1; a daily digest is a v2 option |
| Resend over SMTP | HTTP API, idempotency keys, simple domain verification |

## Not built yet (v2 candidates)

SMS/WhatsApp channels, a digest email, document file uploads, renewal cost reports,
and CORS (needed once a web frontend exists).

## Deployment

One Docker image runs the API, the Celery worker and Celery beat; the start command
selects which. CI (GitHub Actions) proves the migrations, tests and image, Railway
hosts the three services plus Postgres and Redis, and Sentry (optional) collects
errors without request bodies or personal data. Details: [deployment.md](deployment.md).
