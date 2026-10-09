# New-user journey

How someone goes from "never heard of Renewly" to "it quietly saved me from an expired licence", and what the
app does at each step to get them there. Everything marked **built** is in the product today.

## The goal and the one number that matters

A new user succeeds when the **first document is saved with reminders on**, because that is the moment the
product starts working for them (an email will arrive without them doing anything more). Everything below is
designed to get there fast, and then to make the *later* steps (renewing, recording costs, reading reports)
feel natural instead of like homework.

- **Activation:** first document saved. Target: within ten minutes of signing up.
- **Never-lost promise:** after saving, the user is told the exact day the first email will arrive.

## Principles

1. **Show the point before the form.** Say what the app does in three lines before asking for anything.
2. **One obvious next step.** The checklist highlights a single action; everything else is quieter.
3. **Start from something familiar.** "What would you like to track?" beats a blank form.
4. **Defaults that are right.** Reminders pre-chosen (30, 14, 7 and 1 days before), trimmed to days that are still possible.
5. **Progress that can't lie.** Checklist ticks come from real data, not from clicking "done".
6. **Never nag, always allow a way back.** Everything can be skipped; tour and checklist can be replayed from Settings.
7. **Be honest about time.** Steps that only happen on a real renewal are labelled "When you next renew", not left looking overdue.

## The journey at a glance

| # | Stage | User is thinking | What they see | Status |
|---|---|---|---|---|
| 0 | **Discover and sign up** | "Is this for me? What do I get?" | Sign-up page lists the three benefits above the form; timezone picked up automatically | built |
| 1 | **First arrival** | "OK, now what?" | One-time **welcome dialog**: the idea in three steps; *Take a 1-minute tour* or *Skip* | built |
| 2 | **Orientation** | "What's where?" | Optional **tour**: six spotlight stops (summary cards, Add document, Documents, Vehicles, Reports, Settings) | built |
| 3 | **First document** (activation) | "What do I add?" | Empty dashboard offers **quick-start chips** (licence, car insurance, registration, permit, other) that open the form already set up; reminder days chosen on a **calendar** | built |
| 4 | **Reassurance** | "Did that work? When will I hear from you?" | Confirmation: *"“Car insurance” is saved. We'll email you on 19 Oct 2026 (in 10 days), 30 days before expiry, around 8am (Africa/Lagos)."* plus a link to the next step | built |
| 5 | **Make it theirs** | "I'd rather get one email a day" | **Settings**: daily digest, timezone, six-monthly report on/off. Visiting counts as a checklist step | built |
| 6 | **Waiting** | (nothing: they've gone away) | Welcome email (what to do next), then the first reminder, which links straight to the document | built |
| 7 | **First renewal** | "I paid it, now what?" | Reminder email → document → **Mark as renewed** (with optional cost); reminders restart for the new date | built |
| 8 | **Insight** | "Where does my money go?" | **Reports** (by month, type, vehicle, CSV); six-monthly email in January and July | built |
| 9 | **Habit** | "It just works" | Dashboard shows what is expired / expiring / valid; vehicles group related documents | built |
| – | Day-3 nudge to people who never added a document | | | *not built* (see below) |

## Stage detail

### 0. Sign-up
Three short benefits under the heading ("Email reminders before your licence, insurance and permits expire",
"Pick your own reminder days on a calendar", "See what you spend on renewals"). The timezone defaults to the
browser's, with a hint that **reminders arrive at 8am in it**, because that is the one setting people regret
getting wrong.

### 1. Welcome dialog
Shown **once**, only to a user who has not seen it **and** has no documents or vehicles (so existing users who
already have data never see it). Closing it, pressing Escape or choosing *Skip* all mean "skip". Either choice
is remembered immediately on the server, so it never reappears even on another device.

> **Welcome, Ngozi.** Never be caught out by an expired licence, insurance or permit again.
> 1. **Add a document** with its expiry date. 2. **Pick your reminder days** and we'll email you before it expires.
> 3. **Renew it, then mark it as renewed** and we start watching the new date.

### 2. The tour
Six stops, each a spotlight on the real control plus a card (a bottom sheet on phones):

| Stop | Spotlight | Message |
|---|---|---|
| 1 | Status cards | Everything is sorted into expired, expiring soon (within 30 days) and valid |
| 2 | + Add document | Enter the expiry date, pick up to four reminder days on a calendar; emails arrive at 8am your time |
| 3 | Documents | Filter by status, type or vehicle; open one to renew, edit or see history |
| 4 | Vehicles | Keep a car's insurance, registration and permits together |
| 5 | Reports | Spending by month, type and vehicle, CSV download, six-monthly email |
| 6 | Settings | Daily summary, timezone, turn the report off; **replay this tour from here** |

Behaviour: Next / Back / Skip, arrow keys, Escape; steps whose element isn't visible (for example on a small
screen) are skipped; focus moves to the card and is returned afterwards; the spotlight follows the element even
when content loads in above it; it never scrolls pinned elements such as the top bar.

### 3. First document
- Empty dashboard and empty document list show **"What would you like to track first?"** with five chips. Each
  opens the form with the type and a sensible name filled in (`/documents?new=insurance`). A "blank form" link
  remains for anyone who wants it.
- In the form, **reminder days are picked on a calendar** that shows the issue date, expiry date and today,
  shades the days that are allowed, allows up to four, and explains in words why a click was refused (after
  expiry, before issue, already passed, a fifth). New documents start with 30, 14, 7 and 1 days before expiry,
  minus any that would already be in the past.

### 4. Confirmation
Right after saving, the page says exactly when the first email will arrive, in the user's own timezone. If
reminders are off, or every chosen day has passed, it says that instead of leaving the user to find out the hard
way. Until they've looked at Settings it adds *"Choose how you get reminders"*.

### 5 to 9. After the first document
The **getting-started checklist** on the dashboard carries the user the rest of the way:

| Step | Kind | Done when | Button |
|---|---|---|---|
| Create your account | now | always | none |
| Add your first document | now | they have at least one document | Add a document |
| Choose how you get reminders | now | they have opened Settings | Open settings |
| Add a vehicle | optional | they have a vehicle | Add a vehicle |
| Mark a document as renewed | when you next renew | they have recorded a renewal | Open documents |
| Record what a renewal cost | when you next renew | a renewal has a cost | Open documents |

- The card has a progress bar and one highlighted next action.
- The three **"now"** steps decide the headline: **"Get started"** until they're done, then **"You're all set. We'll email you before anything expires."**
- It can be hidden (*Hide*) and brought back from **Settings → Getting started → Show the checklist**. It disappears on its own when every step is done.

## What decides what is shown

| Situation | Welcome dialog | Checklist | Quick-start chips |
|---|---|---|---|
| Brand new (no documents or vehicles, welcome not seen) | yes, once | yes | yes (empty dashboard) |
| Answered the welcome, still no documents | no | yes | yes |
| Has documents, essentials done | no | "You're all set" until finished or hidden | no |
| Hid the checklist | no | no (until restored in Settings) | only if empty |
| Existing user with data from before this existed | no | yes, partly ticked; can be hidden | no |
| Everything done | no | no | no |

## How it is built

- **Remembered on the server** (so it follows the user across devices): `users.onboarding`, a small set of yes/no flags:
  `tour_done`, `checklist_dismissed`, `settings_reviewed`. Changed with `PATCH /auth/me/onboarding`; unknown keys and non-boolean values are rejected.
- **Counted from real data:** `GET /onboarding/progress` returns the number of documents, vehicles, renewals and renewals with a cost (deleted documents excluded). The checklist is computed from these, so it can never disagree with the account.
- **Frontend:** `lib/onboarding.ts` (checklist rules, first-reminder sentence), `components/WelcomeDialog`, `Tour`, `GettingStarted`, `QuickAdd`, `lib/calendar.ts` (reminder-day rules).
- **To change the copy or the order of steps:** edit `lib/onboarding.ts` (checklist), `components/Tour.tsx` (`APP_TOUR`), `components/WelcomeDialog.tsx`.

## Accessibility and small screens
Dialogs trap and restore focus and close on Escape; the tour card is announced as a dialog with a title and
description and gets keyboard focus; checklist progress is a labelled progress bar and completed steps are announced
as "(done)"; nothing relies on colour alone; the tour card becomes a bottom sheet under 640px; the top bar fits a
375px screen. Animations respect *reduce motion*.

## How to know it works (not yet instrumented)
The app has no analytics today, so these are the questions to answer once it does:

| Measure | Why |
|---|---|
| Sign-ups that save a document within 10 minutes | the activation rate; the single most important number |
| Welcome: tour taken vs skipped; tour completed vs abandoned (and at which stop) | whether the tour earns its place |
| Time from sign-up to first document | friction in the form or calendar |
| Checklist hidden before it was finished | whether it reads as helpful or as noise |
| Documents with all four reminders vs fewer | whether defaults are right |
| Reminder email to "marked as renewed" within 7 days | the real outcome: did the product prevent a lapse? |
| Day-7 and day-30 return rate | whether the habit forms |

## Not built yet, in priority order
1. **A nudge email** about three days after sign-up to anyone with no document ("You haven't added anything yet"), once, with the quick-start links. It uses the existing email service; the only care needed is to send it at most once and never to people who have added a document.
2. **A sample document** ("Try it with an example") that can be deleted, for people who want to see the dashboard before typing their own data.
3. **Hints at the moment of use:** a one-time "this restarts your reminders" note the first time someone opens *Mark as renewed*.
4. **One-click unsubscribe** in the six-monthly report email.
5. **Importing** several documents at once (paste or spreadsheet).
