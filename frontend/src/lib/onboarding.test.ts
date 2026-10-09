import { buildChecklist, firstReminderMessage, nextReminder, shouldShowChecklist, shouldShowWelcome } from "./onboarding";

const NONE = { documents: 0, vehicles: 0, renewals: 0, renewals_with_cost: 0 };

describe("buildChecklist", () => {
  it("starts with only the account step done and the 'now' steps outstanding", () => {
    const list = buildChecklist(NONE, {});
    expect(list.steps.map((s) => [s.id, s.done])).toEqual([
      ["account", true],
      ["document", false],
      ["settings", false],
      ["vehicle", false],
      ["renewal", false],
      ["cost", false],
    ]);
    expect([list.done, list.total, list.setUp, list.allDone]).toEqual([1, 6, false, false]);
  });

  it("ticks steps from the user's real data, not from clicks", () => {
    const list = buildChecklist({ documents: 2, vehicles: 1, renewals: 1, renewals_with_cost: 0 }, {});
    expect(list.steps.filter((s) => s.done).map((s) => s.id)).toEqual(["account", "document", "vehicle", "renewal"]);
  });

  it("ticks 'choose how you get reminders' once settings were looked at", () => {
    expect(buildChecklist(NONE, { settings_reviewed: true }).steps.find((s) => s.id === "settings")?.done).toBe(true);
  });

  it("is 'set up' when the essential steps are done, even though renewals haven't happened yet", () => {
    const list = buildChecklist({ ...NONE, documents: 1 }, { settings_reviewed: true });
    expect(list.setUp).toBe(true);
    expect(list.allDone).toBe(false);
  });

  it("is all done only when every step is", () => {
    const all = buildChecklist({ documents: 1, vehicles: 1, renewals: 1, renewals_with_cost: 1 }, { settings_reviewed: true });
    expect([all.done, all.allDone]).toEqual([6, true]);
  });

  it("marks the vehicle step optional and the renewal steps as things that happen later", () => {
    const kinds = Object.fromEntries(buildChecklist(NONE, {}).steps.map((s) => [s.id, s.kind]));
    expect(kinds).toMatchObject({ document: "now", settings: "now", vehicle: "optional", renewal: "later", cost: "later" });
  });

  it("links each outstanding step to the right screen", () => {
    const links = Object.fromEntries(buildChecklist(NONE, {}).steps.map((s) => [s.id, s.href]));
    expect(links).toMatchObject({ document: "/documents?new=1", settings: "/settings", vehicle: "/vehicles", account: null });
  });
});

describe("what to show", () => {
  it("welcomes only people who haven't seen it and have nothing yet", () => {
    expect(shouldShowWelcome(NONE, {})).toBe(true);
    expect(shouldShowWelcome(NONE, { tour_done: true })).toBe(false);
    expect(shouldShowWelcome({ ...NONE, documents: 1 }, {})).toBe(false); // an existing user with data
    expect(shouldShowWelcome({ ...NONE, vehicles: 1 }, {})).toBe(false);
  });

  it("shows the checklist until it is dismissed or finished", () => {
    const partial = buildChecklist(NONE, {});
    expect(shouldShowChecklist(partial, {})).toBe(true);
    expect(shouldShowChecklist(partial, { checklist_dismissed: true })).toBe(false);
    const finished = buildChecklist({ documents: 1, vehicles: 1, renewals: 1, renewals_with_cost: 1 }, { settings_reviewed: true });
    expect(shouldShowChecklist(finished, {})).toBe(false);
  });
});

describe("nextReminder", () => {
  const doc = { expiry_date: "2026-10-31", reminder_offsets: [30, 14, 7, 1] };

  it("is the earliest reminder day that has not passed", () => {
    expect(nextReminder(doc, "2026-10-09")).toEqual({ date: "2026-10-17", daysBefore: 14 });
    expect(nextReminder(doc, "2026-10-18")).toEqual({ date: "2026-10-24", daysBefore: 7 });
  });

  it("counts today as still to come", () => {
    expect(nextReminder(doc, "2026-10-17")).toEqual({ date: "2026-10-17", daysBefore: 14 });
  });

  it("is null when every reminder day has passed or none were chosen", () => {
    expect(nextReminder(doc, "2026-10-31")).toBeNull();
    expect(nextReminder({ ...doc, reminder_offsets: [] }, "2026-10-09")).toBeNull();
  });
});

describe("firstReminderMessage", () => {
  const doc = { title: "Car insurance", expiry_date: "2026-10-31", reminder_offsets: [30, 14, 7, 1] };

  it("tells the user exactly when the first email will arrive", () => {
    expect(firstReminderMessage(doc, "2026-10-09", "Africa/Lagos")).toBe(
      "“Car insurance” is saved. We'll email you on 17 Oct 2026 (in 8 days), 14 days before expiry, around 8am (Africa/Lagos).",
    );
  });

  it("says 'today' when the first reminder is today", () => {
    expect(firstReminderMessage(doc, "2026-10-17", "Africa/Lagos")).toContain("We'll email you today, 14 days before expiry");
  });

  it("explains when reminders are off or all in the past", () => {
    expect(firstReminderMessage({ ...doc, reminder_offsets: [] }, "2026-10-09", "Africa/Lagos")).toContain("Reminders are off");
    expect(firstReminderMessage(doc, "2026-11-05", "Africa/Lagos")).toContain("no email is scheduled");
  });

  it("makes timezone names readable", () => {
    expect(firstReminderMessage(doc, "2026-10-09", "America/Los_Angeles")).toContain("(America/Los Angeles)");
  });
});
