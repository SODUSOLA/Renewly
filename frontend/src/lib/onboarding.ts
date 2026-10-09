// The getting-started journey: which steps exist, which are done, and what to say after the first document.
// Progress comes from the user's real data (see /onboarding/progress), so the checklist can never
// claim something is done that isn't, and ticks itself when the user does things without clicking it.

import type { Doc, Onboarding, OnboardingProgress } from "../api/types";
import { addDays, diffDays, describeOffset } from "./calendar";
import { formatDate } from "./dates";

export type StepKind = "now" | "later" | "optional";

export interface ChecklistStep {
  id: string;
  title: string;
  description: string;
  done: boolean;
  // Where the button takes the user; null for steps that are already done and need no link.
  href: string | null;
  cta: string;
  // "now": do this to be set up. "later": happens naturally on your next real renewal. "optional": nice to have.
  kind: StepKind;
}

export interface ChecklistSummary {
  steps: ChecklistStep[];
  done: number;
  total: number;
  // The "now" steps are finished: the app is working for this user.
  setUp: boolean;
  // Every step is finished.
  allDone: boolean;
}

// The checklist for a user, from what they have created and what they have already seen.
export function buildChecklist(progress: OnboardingProgress, onboarding: Onboarding): ChecklistSummary {
  const steps: ChecklistStep[] = [
    {
      id: "account",
      title: "Create your account",
      description: "You're in.",
      done: true,
      href: null,
      cta: "",
      kind: "now",
    },
    {
      id: "document",
      title: "Add your first document",
      description: "A licence, insurance, registration or permit, with its expiry date. Pick your reminder days on the calendar.",
      done: progress.documents > 0,
      href: "/documents?new=1",
      cta: "Add a document",
      kind: "now",
    },
    {
      id: "settings",
      title: "Choose how you get reminders",
      description: "One email per reminder or a single daily summary, and your timezone.",
      done: onboarding.settings_reviewed === true,
      href: "/settings",
      cta: "Open settings",
      kind: "now",
    },
    {
      id: "vehicle",
      title: "Add a vehicle",
      description: "Group a car's insurance, registration and permits together. Skip this if it doesn't apply.",
      done: progress.vehicles > 0,
      href: "/vehicles",
      cta: "Add a vehicle",
      kind: "optional",
    },
    {
      id: "renewal",
      title: "Mark a document as renewed",
      description: "Do this when you renew something for real. Reminders restart for the new date.",
      done: progress.renewals > 0,
      href: "/documents",
      cta: "Open documents",
      kind: "later",
    },
    {
      id: "cost",
      title: "Record what a renewal cost",
      description: "So your spending reports mean something.",
      done: progress.renewals_with_cost > 0,
      href: "/documents",
      cta: "Open documents",
      kind: "later",
    },
  ];
  const done = steps.filter((s) => s.done).length;
  return {
    steps,
    done,
    total: steps.length,
    setUp: steps.filter((s) => s.kind === "now").every((s) => s.done),
    allDone: done === steps.length,
  };
}

// Whether to show the one-time welcome: only to someone who has not seen it and has nothing yet.
export function shouldShowWelcome(progress: OnboardingProgress, onboarding: Onboarding): boolean {
  return onboarding.tour_done !== true && progress.documents === 0 && progress.vehicles === 0;
}

// Whether to show the checklist card.
export function shouldShowChecklist(summary: ChecklistSummary, onboarding: Onboarding): boolean {
  return onboarding.checklist_dismissed !== true && !summary.allDone;
}

export interface NextReminder {
  date: string;
  daysBefore: number;
}

// The first reminder that will actually be sent for a document: the earliest reminder day that
// is today or later (earlier ones have passed and can never fire). Null if there is none.
export function nextReminder(doc: Pick<Doc, "expiry_date" | "reminder_offsets">, today: string): NextReminder | null {
  const upcoming = doc.reminder_offsets
    .map((daysBefore) => ({ daysBefore, date: addDays(doc.expiry_date, -daysBefore) }))
    .filter((r) => r.date >= today)
    .sort((a, b) => (a.date < b.date ? -1 : 1));
  return upcoming[0] ?? null;
}

// The sentence shown right after the first document is saved: exactly when the first email arrives.
export function firstReminderMessage(doc: Pick<Doc, "title" | "expiry_date" | "reminder_offsets">, today: string, timezone: string): string {
  if (doc.reminder_offsets.length === 0) {
    return `“${doc.title}” is saved. Reminders are off for it, so we won't email you. You can turn them on by editing it.`;
  }
  const next = nextReminder(doc, today);
  if (!next) {
    return `“${doc.title}” is saved, but all of its reminder days have already passed, so no email is scheduled. Edit it to choose later days.`;
  }
  const when = next.date === today ? "today" : `on ${formatDate(next.date)}`;
  const away = diffDays(next.date, today);
  const lead = away > 1 ? ` (in ${away} days)` : "";
  return `“${doc.title}” is saved. We'll email you ${when}${lead}, ${describeOffset(next.daysBefore)}, around 8am (${timezone.replace(/_/g, " ")}).`;
}
