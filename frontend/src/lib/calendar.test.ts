import { vi } from "vitest";
import {
  DEFAULT_OFFSETS,
  MAX_REMINDERS,
  addDays,
  addMonths,
  diffDays,
  earliestReminderDate,
  longDate,
  monthGrid,
  monthTitle,
  todayIn,
  toggleReminder,
  type ReminderContext,
} from "./calendar";

describe("date maths", () => {
  it("adds and subtracts days across month, year and leap boundaries", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(diffDays("2026-10-09", "2026-10-02")).toBe(7);
    expect(diffDays("2026-10-02", "2026-10-09")).toBe(-7);
    expect(diffDays("2027-03-01", "2026-03-01")).toBe(365);
  });

  it("moves between months and names them", () => {
    expect(addMonths("2026-12", 1)).toBe("2027-01");
    expect(addMonths("2026-01", -1)).toBe("2025-12");
    expect(monthTitle("2026-10")).toBe("October 2026");
    expect(longDate("2026-10-15")).toBe("Thursday, 15 October 2026");
  });

  it("builds Monday-first weeks padded with nulls", () => {
    const weeks = monthGrid("2026-10"); // 1 October 2026 is a Thursday
    expect(weeks.every((w) => w.length === 7)).toBe(true);
    expect(weeks[0]).toEqual([null, null, null, "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
    expect(weeks.flat().filter(Boolean)).toHaveLength(31);
    expect(weeks.at(-1)!.at(-1)).toBeNull();
  });

  it("reads today in the user's own timezone", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-08T23:30:00Z")); // 00:30 on the 9th in Lagos (UTC+1), 16:30 on the 8th in Los Angeles
    expect(todayIn("Africa/Lagos")).toBe("2026-10-09");
    expect(todayIn("America/Los_Angeles")).toBe("2026-10-08");
    expect(todayIn("Not/AZone")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    vi.useRealTimers();
  });
});

// A document issued 1 Oct, expiring 31 Oct, viewed on 9 Oct.
const ctx = (over: Partial<ReminderContext> = {}): ReminderContext => ({
  issueDate: "2026-10-01",
  expiryDate: "2026-10-31",
  today: "2026-10-09",
  offsets: [],
  ...over,
});

describe("toggleReminder: valid choices", () => {
  it("adds a day and stores it as days before expiry, largest first", () => {
    const first = toggleReminder("2026-10-24", ctx()); // 7 days before
    expect(first).toMatchObject({ ok: true, offsets: [7] });
    const second = toggleReminder("2026-10-17", ctx({ offsets: [7] })); // 14 days before
    expect(second).toMatchObject({ ok: true, offsets: [14, 7] });
  });

  it("allows today, the expiry day itself and the first allowed day", () => {
    expect(toggleReminder("2026-10-09", ctx())).toMatchObject({ ok: true, offsets: [22] });
    expect(toggleReminder("2026-10-31", ctx())).toMatchObject({ ok: true, offsets: [0] });
  });

  it("removes a day that is already chosen", () => {
    expect(toggleReminder("2026-10-24", ctx({ offsets: [14, 7] }))).toMatchObject({ ok: true, offsets: [14] });
  });

  it("lets a chosen day be removed even if it is now in the past or over the limit", () => {
    const old = ctx({ offsets: [30, 20, 10, 5, 1] }); // five reminders (an older default); 30 days before is 1 Oct
    expect(toggleReminder("2026-10-01", old)).toMatchObject({ ok: true, offsets: [20, 10, 5, 1] });
  });
});

describe("toggleReminder: the error messages", () => {
  it("after the expiry date", () => {
    expect(toggleReminder("2026-11-02", ctx())).toEqual({
      ok: false,
      message: "Reminders must be on or before the expiry date (31 Oct 2026).",
    });
  });

  it("before the issue date", () => {
    const result = toggleReminder("2026-09-20", ctx({ today: "2026-09-01" }));
    expect(result).toEqual({ ok: false, message: "That's before the document was issued (1 Oct 2026). Pick a day after it." });
  });

  it("in the past", () => {
    const result = toggleReminder("2026-10-05", ctx());
    expect(result).toEqual({ ok: false, message: "That day has already passed, so we couldn't send a reminder then. Pick today or later." });
  });

  it("more than a year before expiry", () => {
    const far = ctx({ issueDate: null, expiryDate: "2027-12-01", today: "2026-01-01" });
    expect(toggleReminder("2026-11-30", far)).toEqual({ ok: false, message: "Reminders can be at most 365 days before the expiry date." });
  });

  it("a fifth reminder", () => {
    const full = ctx({ offsets: [20, 14, 7, 1] });
    expect(MAX_REMINDERS).toBe(4);
    expect(toggleReminder("2026-10-12", full)).toEqual({ ok: false, message: "You can choose up to 4 reminders. Remove one to pick another." });
  });

  it("reports the problem that matters first: expiry, then issue, then past", () => {
    expect(toggleReminder("2026-12-01", ctx()).message).toMatch(/on or before the expiry/);
    expect(toggleReminder("2026-09-01", ctx()).message).toMatch(/before the document was issued/);
  });

  it("does not mention an issue date when there is none", () => {
    expect(toggleReminder("2026-10-05", ctx({ issueDate: null })).message).toMatch(/already passed/);
  });
});

describe("earliestReminderDate", () => {
  it("is the latest of today, the issue date and 365 days before expiry", () => {
    expect(earliestReminderDate(ctx())).toBe("2026-10-09");
    expect(earliestReminderDate(ctx({ issueDate: "2026-10-20" }))).toBe("2026-10-20");
    expect(earliestReminderDate(ctx({ issueDate: null, expiryDate: "2028-01-01", today: "2026-01-01" }))).toBe("2027-01-01");
  });

  it("matches the defaults the form starts with", () => {
    expect(DEFAULT_OFFSETS).toEqual([30, 14, 7, 1]);
  });
});
