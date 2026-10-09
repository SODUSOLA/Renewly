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

## Email

Everything the app emails lives in two places that never mix:

| Where | What | Changed by |
|---|---|---|
| `app/modules/notifications/templates/` | **All wording and layout.** Each email is `<name>.subject`, `<name>.html`, `<name>.txt`, sharing `base.html` (layout), `_macros.html` (button) and `_footer.txt` | Anyone editing copy or design; no code involved |
| `app/modules/notifications/service.py` | **One function per email** (`build_welcome_email`, `send_password_reset_email`, `render_expiry_digest`, `build_cost_report_email`...): collects the data, renders its template, returns/sends the message | Developers |

`templating.py` is the small engine between them (Jinja2): HTML is escaped automatically, a template that
uses a variable the code didn't provide is an error rather than a blank, and subjects are collapsed to
one line so a value containing a line break can't inject headers. `email.py` is transport only (Resend).

| Email | Template | Function that uses it | Triggered by |
|---|---|---|---|
| Welcome | `welcome` | `send_welcome_email` | `POST /auth/register` (background task) |
| Password reset | `password_reset` | `send_password_reset_email` | `POST /auth/forgot-password` |
| Password changed | `password_changed` | `send_password_changed_email` | `POST /auth/reset-password` |
| Reminder | `expiry_reminder` | `render_expiry_reminder` | hourly reminder job |
| Daily digest | `expiry_digest` | `render_expiry_digest` | hourly reminder job (digest users) |
| Six-monthly report | `cost_report` | `build_cost_report_email` | hourly report job, first week of Jan/Jul |

Emails sent from a request (welcome, reset, password changed) run as background tasks and never raise: a
provider outage must not break sign-up or a reset. Look at every design without sending anything with
`python -m app.modules.notifications.preview`; the tests render every template with the same sample data, so
a broken template fails the build.

### The six-monthly report

`reports/periodic.py`. Celery Beat runs it hourly at minute 20, but outside the first seven days of January and
July it returns immediately. Inside that window each user is handled from 08:00 local time, and the week-long
window means a day of downtime costs nobody their report. "Once per user per period" is enforced like reminders:
a row in `email_dispatch` (unique on user, kind, period such as `2026-H1`) is claimed with one atomic
`INSERT ... ON CONFLICT` before sending; `sent` and `skipped` rows are never retaken, `failed` and stale `pending` rows
are. Users with `report_emails` off, inactive users, and accounts with nothing to report are not sent anything
(the last are recorded as `skipped` so they aren't re-evaluated every hour). The "coming up" list estimates each cost
from the document's last recorded renewal cost and says it is an estimate.

## The web app

`frontend/` is a single-page React app (Vite, TypeScript) that talks to the API over HTTPS. There is no
server-side rendering; the built files are static, and nginx (or Vercel) serves them with a fallback to
`index.html` so deep links work.

| Piece | Choice | Why |
|---|---|---|
| Server data | TanStack Query | Caching, loading and error states, and invalidation after changes (renewing a document refreshes the dashboard, reports and checklist) |
| Routing | React Router; signed-in pages under one `RequireAuth` guard | Signed-out visitors are sent to sign-in and returned to where they were headed |
| Auth | Access token in memory, refresh token in an `HttpOnly` cookie (see Sessions) | Nothing an injected script could steal is in storage; a reload or an expired token heals silently |
| API access | One `fetch` wrapper (`src/api/client.ts`) | Adds the token, parses the uniform error shape, exposes field errors and `Retry-After`, refreshes once on a 401 |
| Dates | Plain `YYYY-MM-DD` strings, never `Date` objects | A `Date` built from a bare date shifts by a day in some timezones |
| Reminder days | A calendar (`lib/calendar.ts`) converting dates to "days before expiry" | The server stores offsets; the calendar only changes how they are entered |
| Styling | One CSS file with design tokens, automatic dark mode | No UI-kit dependency; fits a 375px phone |

**First-run journey.** The welcome dialog, spotlight tour, checklist and quick-start chips are described in
[ux-journey.md](ux-journey.md). Two small backend pieces support them: `users.onboarding` (yes/no flags remembered
per user, so the journey follows them between devices) and `GET /onboarding/progress` (counts of documents,
vehicles and renewals). The checklist is computed from those counts rather than stored, so it cannot disagree
with the account.

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

### Daily digest

Each user chooses `each` (default) or `digest`. The job groups the day's due reminders by
user, then:

- **`each`:** claim, send and record every reminder separately (above).
- **`digest`:** claim every due reminder for that user, send **one** email covering the ones
  that were won, then mark all of them `sent` (or all `failed`) together.

The safety properties carry over unchanged because the claim is still per reminder: a
reminder already sent (even individually, before the user switched style) is left out; two
workers cannot both claim it; a failed digest is retried as one email on the next run. The
provider idempotency key is a hash of *which* reminders the digest covers, so a retry of the
same set cannot be delivered twice. A digest is only sent on a day when something is due; it
is a batching of reminders, not a daily status report.

Consequences worth knowing:

- Running the job any number of times is harmless (this is what makes hourly runs safe).
- A failed send is retried on each later run that day while the reminder is still due; after that day the offset has passed.
- The dedup key contains `expiry_date`, so **renewing a document automatically re-arms** its reminders. No cleanup needed.
- If the system is down for a whole day, that day's reminders are missed rather than sent late in bulk. This is deliberate: it avoids a flood of stale emails after an outage.
- Documents created inside an offset window (e.g. 20 days before expiry with a 30-day offset) do not get the missed offset; they get the next one.

## Sessions

Two tokens, because they answer different questions:

| | Access token | Refresh token |
|---|---|---|
| Lives | 15 minutes | 30 days sliding, 90 days max |
| Held in | Page memory | `HttpOnly` cookie (invisible to JavaScript) |
| Sent to | Every API call, as `Authorization: Bearer` | Only `/auth/refresh` and `/auth/logout` (cookie `Path=/auth`) |
| Server state | None (a signed JWT) | A hashed row in `refresh_tokens` |
| If stolen | Useful for at most 15 minutes | Detected when used twice; revokes the login |

```text
page load ─▶ POST /auth/refresh (cookie) ─▶ access token in memory ─▶ GET /auth/me
any call  ─▶ 401 (token expired) ─▶ POST /auth/refresh ─▶ retry the call once
```

Rotation detail: each refresh marks the presented row `rotated_at` and inserts a new row
in the same `family_id`. A second use of a rotated row is theft, unless it arrives within
10 seconds (two tabs refreshing together share one cookie jar), in which case the caller
gets an access token and no new cookie. A daily Celery task deletes rows that expired more
than a day ago; rotated and revoked rows are kept until then because detection needs them.

**Hosting constraint.** A cookie is only dependable when the web app and the API are on the
same *site* (e.g. `app.example.com` and `api.example.com`). The default `*.up.railway.app`
names are different sites, which makes the refresh cookie a third-party cookie that Safari
and Firefox block; see [deployment.md](deployment.md#sessions-and-cookies).

## Time handling

- Timestamps are stored in UTC (`timestamptz`).
- Expiry dates are plain dates, with no timezone.
- "Today" is computed **per user** from their IANA timezone (`app/common/dates.py`). The status shown on a document, the dashboard and the reminder job all use the same calculation, so they cannot disagree.
- The server's own date is never used for expiry maths.

## Security decisions

| Concern | Decision |
|---|---|
| Passwords | argon2; never stored or logged in plain text |
| Login | Short-lived JWT access token (15 min, HS256) plus a rotating refresh token in an `HttpOnly`, `Secure`, `SameSite` cookie scoped to `/auth`; identical error for wrong email and wrong password; dummy hash on unknown email to equalise timing |
| Sessions | Refresh tokens are stored hashed, grouped per login. Reuse of a rotated token revokes the whole login; logout and password reset revoke sessions; cookie-using endpoints check `Origin` (CSRF) |
| Password reset | Random token, only its SHA-256 stored, 1 hour expiry, single use, spends all siblings; the request endpoint answers identically for unknown emails |
| Data isolation | Every query filters by the current user; other people's rows return `404`, not `403` |
| Abuse | Redis rate limits per IP and per email (hashed in keys); fails open if Redis is down. The IP comes from `X-Forwarded-For` counted from the right by the number of trusted proxies (`TRUSTED_PROXY_HOPS`), so a forged header cannot pick a fresh bucket |
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
| Templates as files in one folder, not strings in code | Copy and design can change without touching Python, and every email shares one layout |
| Six-month report on fixed calendar halves (Jan/Jul) | Everyone gets it at the same, memorable time; per-user anniversaries would scatter emails across the year for no benefit |
| Soft delete for documents only | Documents carry history; vehicles are simple records and are hard-deleted |
| Hourly job + local 08:00 gate, not one daily run | Users in different timezones all get a morning email, and a transient failure is retried within the day |
| Per-document emails by default, digest opt-in | Per-document was the simplest correct v1 and keeps existing users' behaviour; the digest is a per-user setting that batches the same reminders |
| Resend over SMTP | HTTP API, idempotency keys, simple domain verification |

## Not built yet (v2 candidates)

SMS/WhatsApp channels, a digest email, document file uploads, renewal cost reports,
and CORS (needed once a web frontend exists).

## Deployment

One Docker image runs the API, the Celery worker and Celery beat; the start command
selects which. CI (GitHub Actions) proves the migrations, tests and image, Railway
hosts the three services plus Postgres and Redis, and Sentry (optional) collects
errors without request bodies or personal data. Details: [deployment.md](deployment.md).
