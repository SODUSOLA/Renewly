// Calendar maths and the rules for choosing reminder days.
//
// Dates are plain "YYYY-MM-DD" strings. Everything goes through UTC so a user's own timezone
// can never shift a date by a day. A reminder is stored as "N days before expiry"; the calendar
// shows it as a date, and these helpers convert between the two.

import { formatDate } from "./dates";

// Most reminders a person can choose per document in the calendar.
export const MAX_REMINDERS = 4;
// The server accepts reminders up to a year before expiry.
export const MAX_DAYS_BEFORE = 365;
// What a new document starts with: a month, two weeks, a week and the day before.
export const DEFAULT_OFFSETS = [30, 14, 7, 1];

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Today's date where the user lives ("2026-10-09"); falls back to the browser's timezone.
export function todayIn(timezone?: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  }
}

function utc(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

// "2026-10-31" + 1 -> "2026-11-01"
export function addDays(iso: string, days: number): string {
  return new Date(utc(iso) + days * 86_400_000).toISOString().slice(0, 10);
}

// Whole days from b to a: diffDays("2026-10-09", "2026-10-02") === 7
export function diffDays(a: string, b: string): number {
  return Math.round((utc(a) - utc(b)) / 86_400_000);
}

// "2026-10-09" -> "2026-10"
export function monthOf(iso: string): string {
  return iso.slice(0, 7);
}

// "2026-12" + 1 -> "2027-01"
export function addMonths(month: string, count: number): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + count, 1)).toISOString().slice(0, 7);
}

// "2026-10" -> "October 2026"
export function monthTitle(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

// "2026-10-15" -> "Thursday, 15 October 2026"
export function longDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]}, ${d} ${MONTHS[m - 1]} ${y}`;
}

// Rows of seven days (Monday first) for a month; null pads the first and last weeks.
export function monthGrid(month: string): (string | null)[][] {
  const [y, m] = month.split("-").map(Number);
  const leading = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: (string | null)[] = [...Array(leading).fill(null)];
  for (let day = 1; day <= length; day++) cells.push(`${month}-${String(day).padStart(2, "0")}`);
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export interface ReminderContext {
  issueDate: string | null;
  expiryDate: string;
  today: string;
  // Reminders already chosen, as days before expiry.
  offsets: number[];
  max?: number;
}

export type ReminderCheck =
  | { ok: true; offsets: number[]; message: string }
  | { ok: false; message: string };

// The earliest date a NEW reminder may be on: not before the document was issued, not in
// the past (it could never be sent), and not more than a year before expiry.
export function earliestReminderDate(ctx: Pick<ReminderContext, "issueDate" | "expiryDate" | "today">): string {
  const floors = [ctx.today, addDays(ctx.expiryDate, -MAX_DAYS_BEFORE)];
  if (ctx.issueDate) floors.push(ctx.issueDate);
  return floors.reduce((a, b) => (a > b ? a : b));
}

// What happens when the user clicks `date`: it is added, removed (if already chosen), or
// rejected with a message that says exactly why.
export function toggleReminder(date: string, ctx: ReminderContext): ReminderCheck {
  const max = ctx.max ?? MAX_REMINDERS;
  const offset = diffDays(ctx.expiryDate, date);

  // Clicking a chosen day removes it, whatever else is true of it.
  if (ctx.offsets.includes(offset)) {
    return { ok: true, offsets: ctx.offsets.filter((o) => o !== offset), message: `Removed the reminder on ${formatDate(date)}.` };
  }
  if (date > ctx.expiryDate) {
    return { ok: false, message: `Reminders must be on or before the expiry date (${formatDate(ctx.expiryDate)}).` };
  }
  if (ctx.issueDate && date < ctx.issueDate) {
    return { ok: false, message: `That's before the document was issued (${formatDate(ctx.issueDate)}). Pick a day after it.` };
  }
  if (date < ctx.today) {
    return { ok: false, message: "That day has already passed, so we couldn't send a reminder then. Pick today or later." };
  }
  if (offset > MAX_DAYS_BEFORE) {
    return { ok: false, message: `Reminders can be at most ${MAX_DAYS_BEFORE} days before the expiry date.` };
  }
  if (ctx.offsets.length >= max) {
    return { ok: false, message: `You can choose up to ${max} reminders. Remove one to pick another.` };
  }
  const offsets = [...ctx.offsets, offset].sort((a, b) => b - a);
  return { ok: true, offsets, message: `Reminder added for ${formatDate(date)}, ${describeOffset(offset)}.` };
}

// 0 -> "on the expiry day", 1 -> "1 day before expiry", 14 -> "14 days before expiry"
export function describeOffset(offset: number): string {
  if (offset === 0) return "on the expiry day";
  return `${offset} ${offset === 1 ? "day" : "days"} before expiry`;
}
