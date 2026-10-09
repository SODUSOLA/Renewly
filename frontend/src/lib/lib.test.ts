import { addYears, describeDaysLeft, formatDate, formatNaira } from "./dates";
import { typeLabel } from "./status";

describe("dates", () => {
  it("formats an ISO date without shifting the day", () => {
    expect(formatDate("2027-03-01")).toBe("1 Mar 2027");
    expect(formatDate("2026-12-31")).toBe("31 Dec 2026");
    expect(formatDate(null)).toBe("");
  });

  it("adds years, including across a leap day", () => {
    expect(addYears("2027-03-01", 1)).toBe("2028-03-01");
    expect(addYears("2027-12-31", 1)).toBe("2028-12-31");
  });

  it("describes days left in words", () => {
    expect(describeDaysLeft(0)).toBe("today");
    expect(describeDaysLeft(1)).toBe("tomorrow");
    expect(describeDaysLeft(12)).toBe("in 12 days");
    expect(describeDaysLeft(-1)).toBe("yesterday");
    expect(describeDaysLeft(-5)).toBe("5 days ago");
  });
});

describe("formatNaira", () => {
  it("always shows two decimals with thousands separators", () => {
    expect(formatNaira("15000.5")).toBe("₦15,000.50");
    expect(formatNaira("15000")).toBe("₦15,000.00");
    expect(formatNaira("oops")).toBe("oops");
  });
});

describe("typeLabel", () => {
  it("uses the custom label only for custom documents", () => {
    expect(typeLabel("custom", "Gym card")).toBe("Gym card");
    expect(typeLabel("permit", "ignored")).toBe("Permit");
  });
});

describe("percentChange", () => {
  it("rounds to a whole percent and handles decreases", async () => {
    const { percentChange } = await import("./dates");
    expect(percentChange("187000.75", "100000.00")).toBe(87);
    expect(percentChange("80", "100")).toBe(-20);
    expect(percentChange("100", "100")).toBe(0);
  });

  it("has nothing to compare when last year had no spending", async () => {
    const { percentChange } = await import("./dates");
    expect(percentChange("500", "0.00")).toBeNull();
  });
});
