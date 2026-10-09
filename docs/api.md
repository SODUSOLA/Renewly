# API reference

Base URL in development: `http://localhost:8000`. Interactive docs: `/docs`.
All request and response bodies are JSON.

## Conventions

**Browsers.** Calls from a web page are only accepted from the origins in the server's `CORS_ORIGINS`.
The `X-Request-ID` and `Retry-After` response headers are readable by the page.

**Authentication.** Log in to get a token and send it on every protected request:

```text
Authorization: Bearer <access_token>
```

Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 15). Login also sets
an **`HttpOnly` refresh cookie** (30 days, sliding, 90 days at most) that
`POST /auth/refresh` trades for a new access token, so users stay signed in without
JavaScript ever holding a long-lived credential. See [Sessions](#sessions) below.
Everything except `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`,
`/auth/forgot-password`, `/auth/reset-password` and `/health*` requires an access token.

**Ownership.** You only ever see your own data. Asking for someone else's vehicle
or document returns `404`, exactly as if it did not exist.

**Errors.** Every error has the same shape:

```json
{ "detail": "Vehicle not found", "code": "not_found", "request_id": "3f2a..." }
```

For validation errors (`422`) `detail` is a list of field problems. Quote
`request_id` (also sent as the `X-Request-ID` response header) when reporting a
problem. You may send your own `X-Request-ID` to trace a call across systems.

| Status | `code` | Meaning |
|---|---|---|
| 400 | `bad_request` | Rejected, e.g. an invalid or expired reset token |
| 401 | `unauthorized` | Missing, invalid or expired token; or wrong email/password |
| 404 | `not_found` | Does not exist, was deleted, or is not yours |
| 405 | `method_not_allowed` | Wrong HTTP method for that path |
| 409 | `conflict` | Duplicate (email already registered, plate already used) |
| 422 | `validation_error` | Invalid input or a broken business rule |
| 429 | `rate_limited` | Too many requests; see `Retry-After` |
| 500 | `internal_error` | Our fault; no details are exposed, use `request_id` |

**Rate limits.** Over the limit you get `429` with a `Retry-After` header (seconds).
Per-IP limits use the client's real address as seen by the server's own proxies; a client-supplied `X-Forwarded-For` cannot change which bucket a request falls in.

| Endpoint | Limit |
|---|---|
| `POST /auth/login` | 10 attempts / 15 min per email, 30 / min per IP |
| `POST /auth/register` | 10 / hour per IP |
| `POST /auth/forgot-password` | 3 / hour per email, 5 / hour per IP |
| `POST /auth/reset-password` | 10 / hour per IP |

**Dates and time.** Dates are `YYYY-MM-DD`. "Today" always means today **in the
user's timezone** (set at sign-up; an IANA name such as `Africa/Lagos`).
Timestamps (`created_at`...) are UTC.

---

## Auth

### `POST /auth/register` → 201
```json
{ "email": "ada@example.com", "password": "correct-horse", "full_name": "Ada Obi",
  "timezone": "Africa/Lagos" }
```
`timezone` is optional (defaults to the server's `DEFAULT_TIMEZONE`). Password: 8-128 characters.
Emails are case-insensitive. Returns the user (never the password):
```json
{ "id": "…", "email": "ada@example.com", "full_name": "Ada Obi",
  "timezone": "Africa/Lagos", "reminder_style": "each", "report_emails": true,
  "onboarding": {}, "created_at": "2026-10-08T09:00:00Z" }
```
Errors: `409` email already registered, `422` bad timezone or short password.

### `POST /auth/login` → 200
```json
{ "email": "ada@example.com", "password": "correct-horse" }
```
```json
{ "access_token": "eyJ…", "token_type": "bearer", "expires_in": 900 }
```
`expires_in` is in seconds. The response also sets the refresh cookie (below); the refresh
token is never in the JSON body. Any failure is a `401 "Incorrect email or password"`;
it never says which part was wrong.

### `GET /auth/me` → 200
Returns the logged-in user (same shape as register).

### `PATCH /auth/me` → 200
Change your own settings. Send only the fields you want to change; `null` is rejected
(omit the field instead). The email address cannot be changed here.
```json
{ "reminder_style": "digest", "timezone": "Europe/London", "full_name": "Ada Obi" }
```
| Field | Values |
|---|---|
| `reminder_style` | `each` (default): one email per document reminder. `digest`: one email a day listing everything due |
| `report_emails` | `true` (default) to receive the six-monthly spending report, `false` to opt out |
| `timezone` | An IANA name; it decides when "8am" and "today" are for you, from the next reminder run |
| `full_name` | 1-150 characters |

Returns the updated user. `422` for an unknown timezone or style.

### `POST /auth/refresh` → 200
No body. The browser sends the refresh cookie automatically (use `credentials: "include"`).
Returns a new access token in the same shape as login, and sets a **new** refresh cookie
(the old one stops working). `401` if the cookie is missing, expired, revoked or was
already used; the response also deletes the cookie. Rate limit: 60 / min per IP.

### `POST /auth/logout` → 204
Revokes this device's login and deletes the cookie. Harmless when already signed out.
Other devices stay signed in.

### `PATCH /auth/me/onboarding` → 200
Remember what the user has seen in the getting-started journey (used by the web app). Boolean flags only:
`tour_done`, `checklist_dismissed`, `settings_reviewed`. Flags are merged with what is already stored; unknown keys,
`null` and non-boolean values are `422`. The result is the updated user, whose `onboarding` object holds the flags.

### `POST /auth/forgot-password` → 202
```json
{ "email": "ada@example.com" }
```
Always answers `{"message": "If that email is registered, a reset link has been sent."}`,
whether or not the account exists, so it cannot be used to find registered emails.
The email contains a link to the web app's reset page (or the bare token when `FRONTEND_URL` is not configured), valid for 1 hour.

### `POST /auth/reset-password` → 200
```json
{ "token": "<from the email>", "new_password": "brand-new-pass" }
```
`400` if the token is unknown, expired or already used. Using a token invalidates
every other outstanding reset token for that account.

---

## Sessions

Login sets one cookie, `renewly_refresh`:

| Attribute | Value | Why |
|---|---|---|
| `HttpOnly` | yes | Page scripts cannot read it, so an injected script cannot steal the login |
| `Secure` | in production | Only sent over HTTPS |
| `SameSite` | `Lax` (configurable) | Not sent on cross-site requests; see `COOKIE_SAMESITE` |
| `Path` | `/auth` | Only the auth endpoints ever receive it |
| `Max-Age` | 30 days | Slides forward each time it is used |

How it behaves:

- **Rotation.** Every `/auth/refresh` returns a new refresh token and retires the old one.
- **Theft detection.** Presenting a retired token again (after a 10-second grace window for two tabs refreshing at once) means a copy was stolen, so that login's whole chain is revoked and the real user signs in again.
- **Limits.** 30 days idle, 90 days absolute, then a fresh sign-in is required.
- **Sign-out everywhere.** Resetting the password revokes every login for the account.
- **CSRF.** `/auth/refresh` and `/auth/logout` reject browser requests whose `Origin` is not in `CORS_ORIGINS` (`403`). Requests with no `Origin` (curl, apps) are allowed. This backs up the `SameSite` cookie.
- **CORS.** Browser pages call these endpoints with credentials, so the API sends `Access-Control-Allow-Credentials: true` for the allowed origins only.

## Vehicles

A vehicle: `id, nickname, plate_number, make, model, year, created_at, updated_at`.

| Method and path | Purpose |
|---|---|
| `GET /vehicles` | List your vehicles |
| `POST /vehicles` → 201 | Create |
| `GET /vehicles/{id}` | Fetch one |
| `PATCH /vehicles/{id}` | Change only the fields you send |
| `DELETE /vehicles/{id}` → 204 | Delete (its documents are kept, just detached) |

```json
{ "nickname": "Corolla", "plate_number": "abc 123 xy", "make": "Toyota", "model": "Corolla", "year": 2018 }
```
`nickname` and `plate_number` are required on create. The plate is stored
uppercase without spaces (`ABC123XY`). The same plate twice for one user is a `409`
(two different users may share one). `year` is 1900-2100. On `PATCH`, `nickname`
and `plate_number` cannot be set to `null`.

---

## Documents

A document:

| Field | Notes |
|---|---|
| `id`, `created_at`, `updated_at` | |
| `vehicle_id` | Optional link to one of your vehicles |
| `type` | `driver_license`, `insurance`, `vehicle_registration`, `permit`, `custom` |
| `custom_type_label` | Required when `type` is `custom`; cleared for other types |
| `title` | Required, up to 150 characters |
| `document_number`, `notes` | Optional |
| `issue_date` | Optional; `expiry_date` cannot be earlier |
| `expiry_date` | Required |
| `reminder_offsets` | Days before expiry to remind; default `[90, 30, 14, 7, 1]` |
| `days_left` | **Derived.** Negative means already expired |
| `status` | **Derived.** `expired` (< 0 days), `expiring_soon` (0-30), `valid` (> 30) |

Offsets: each 0-365 (0 = on the day itself), at most 10, stored de-duplicated and
largest first. `[]` turns reminders off for that document.

| Method and path | Purpose |
|---|---|
| `GET /documents` | List, soonest expiry first. Filters: `?vehicle_id=…&type=…&status=…` |
| `POST /documents` → 201 | Create |
| `GET /documents/{id}` | Fetch one |
| `PATCH /documents/{id}` | Change only the fields you send; rules are re-checked on the merged result |
| `DELETE /documents/{id}` → 204 | Soft delete (hidden from the API, row kept) |
| `POST /documents/{id}/renew` | Mark as renewed |
| `GET /documents/{id}/renewals` | Renewal history, newest first |

```json
{ 
  "type": "insurance", 
  "title": "Car insurance", 
  "vehicle_id": "…",
  "issue_date": "2026-03-01", 
  "expiry_date": "2027-03-01",
  "reminder_offsets": [30, 7, 1] 
}
```
`422` when: `custom` has no label, expiry is before issue, `vehicle_id` is not one of
your vehicles, or an offset is out of range.

### `POST /documents/{id}/renew`
```json
{ 
  "new_expiry": "2028-03-01", 
  "cost": "15000.50",
  "notes": "Annual premium" 
}
```
`cost` and `notes` are optional. `new_expiry` must be **later** than the current expiry
(`422` otherwise, and nothing is recorded). On success the expiry moves forward, a
history entry is written (previous expiry, new expiry, date renewed, cost) and the
same reminder offsets apply again for the new date. Returns the updated document.

---

## Dashboard

### `GET /dashboard` → 200
```json
{
  "today": "2026-10-08",
  "counts": 
      { "expired": 1, 
        "expiring_soon": 2, 
        "valid": 5, 
        "total": 8 
      },
  "expired": [ /* documents */ ],
  "expiring_soon": [ /* documents */ ],
  "valid": [ /* documents */ ]
}
```
Each list holds full documents (with `days_left` and `status`), soonest expiry
first, so the most overdue items lead the `expired` list. Soft-deleted documents
are excluded.

---

## Onboarding

### `GET /onboarding/progress` → 200
```json
{ "documents": 2, "vehicles": 1, "renewals": 1, "renewals_with_cost": 0 }
```
Counts of the user's own live documents, vehicles and renewals (deleted documents and their renewals are not counted),
which the web app turns into the getting-started checklist.

## Health

| Path | Purpose |
|---|---|
| `GET /health` | Liveness: `{"status": "ok"}` while the process runs |
| `GET /health/ready` | Readiness: `200 {"status": "ready"}`, or `503` if the database is unreachable |

## Emails the app sends

| Email | When | Can be turned off? |
|---|---|---|
| Welcome | Right after sign-up | No |
| Password reset | After `POST /auth/forgot-password` for a real account | No |
| Password changed | After a successful `POST /auth/reset-password`: tells the owner, with a link to reset again if it wasn't them | No (security) |
| Reminder / daily digest | When a document hits one of its reminder days (see below) | Per document (empty reminder list) or via `reminder_style` |
| Six-monthly report | First week of **January** (covering July to December) and **July** (covering January to June), from 08:00 in the user's timezone: spending, biggest categories and vehicles, and what expires in the next six months with a rough cost | Yes: `report_emails: false` |

Accounts with no renewals in the period and nothing expiring soon get no report. Each email is sent
at most once per user per period.

## Reminder emails

Not an endpoint, but part of the contract: a reminder is due when a document's days left
(in the owner's timezone) equals one of its offsets, from 08:00 local time onward. Each
reminder is delivered once per document, offset and expiry date. With `reminder_style:
"each"` every reminder is its own email; with `"digest"` all of that user's reminders due
on the same day arrive in **one** email, most urgent first (a day with one due document
reads like an ordinary reminder, and a day with none sends nothing).
Deleted documents and deactivated users never get reminders.
