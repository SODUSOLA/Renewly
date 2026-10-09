import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";
import { ReminderCalendar } from "./ReminderCalendar";

// A document issued 1 Oct 2026, expiring 31 Oct 2026, looked at on 9 Oct 2026.
const DOC = { issueDate: "2026-10-01" as string | null, expiryDate: "2026-10-31", today: "2026-10-09" };

// func to render the calendar the way the form uses it: it owns no state, the parent does
function Harness({ initial = [] as number[], onChange = vi.fn(), ...rest }: Partial<typeof DOC> & { initial?: number[]; onChange?: (o: number[]) => void }) {
  const [offsets, setOffsets] = useState(initial);
  return (
    <ReminderCalendar
      {...DOC}
      {...rest}
      offsets={offsets}
      onChange={(next) => {
        setOffsets(next);
        onChange(next);
      }}
    />
  );
}

const day = (label: RegExp) => screen.getByRole("button", { name: label });

describe("ReminderCalendar: what it shows", () => {
  it("opens on today's month and marks today, the issue date and the expiry date", () => {
    render(<Harness />);
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
    expect(day(/^Friday, 9 October 2026\. Today/)).toBeInTheDocument();
    expect(day(/^Thursday, 1 October 2026\. Issue date/)).toBeInTheDocument();
    expect(day(/^Saturday, 31 October 2026\. Expiry date/)).toBeInTheDocument();
    // The markers are text, not just colour.
    expect(within(day(/^Saturday, 31 October 2026\. Expiry date/)).getByText("Expires")).toBeInTheDocument();
    expect(within(day(/^Thursday, 1 October 2026\. Issue date/)).getByText("Issued")).toBeInTheDocument();
  });

  it("describes days that cannot take a reminder", () => {
    render(<Harness />);
    expect(day(/^Monday, 5 October 2026\. Not available/)).toBeInTheDocument(); // in the past
    expect(day(/^Monday, 12 October 2026$/)).toBeInTheDocument(); // allowed: no extra remark
  });

  it("shows the chosen reminders as dates with how long before expiry", () => {
    render(<Harness initial={[14, 7]} />);
    expect(screen.getByText("2 of 4 reminders")).toBeInTheDocument();
    expect(screen.getByText("24 Oct 2026 · 7 days before expiry")).toBeInTheDocument();
    expect(screen.getByText("17 Oct 2026 · 14 days before expiry")).toBeInTheDocument();
    expect(day(/^Saturday, 24 October 2026\. Reminder, 7 days before expiry/)).toHaveAttribute("aria-pressed", "true");
  });

  it("says plainly when there are no reminders", () => {
    render(<Harness />);
    expect(screen.getByText(/you won't be emailed about this document/)).toBeInTheDocument();
  });

  it("hides the issue-date shortcut when there is no issue date", () => {
    render(<Harness issueDate={null} />);
    expect(screen.queryByRole("button", { name: "Issue date" })).not.toBeInTheDocument();
    expect(screen.getByText(/between 9 Oct 2026 and 31 Oct 2026/)).toBeInTheDocument();
  });

  it("opens on the expiry month for a document that has already expired", () => {
    render(<Harness expiryDate="2026-08-15" issueDate={null} />);
    expect(screen.getByRole("heading", { name: "August 2026" })).toBeInTheDocument();
  });
});

describe("ReminderCalendar: choosing days", () => {
  it("adds a reminder when an allowed day is clicked, and tells the user", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(day(/^Saturday, 24 October 2026/));
    expect(onChange).toHaveBeenLastCalledWith([7]);
    expect(screen.getByRole("status")).toHaveTextContent("Reminder added for 24 Oct 2026, 7 days before expiry.");
    expect(screen.getByText("1 of 4 reminders")).toBeInTheDocument();
  });

  it("removes a reminder when its day is clicked again, or from its chip", async () => {
    const onChange = vi.fn();
    render(<Harness initial={[14, 7]} onChange={onChange} />);
    await userEvent.click(day(/^Saturday, 24 October 2026/));
    expect(onChange).toHaveBeenLastCalledWith([14]);
    await userEvent.click(screen.getByRole("button", { name: "Remove the reminder on 17 Oct 2026" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("clears everything with one click", async () => {
    const onChange = vi.fn();
    render(<Harness initial={[14, 7, 1]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.getByText("0 of 4 reminders")).toBeInTheDocument();
  });

  it("allows the expiry day itself and today", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(day(/^Saturday, 31 October 2026/));
    expect(onChange).toHaveBeenLastCalledWith([0]);
    await userEvent.click(day(/^Friday, 9 October 2026/));
    expect(onChange).toHaveBeenLastCalledWith([22, 0]);
    expect(screen.getByText("31 Oct 2026 · on the expiry day")).toBeInTheDocument();
  });
});

describe("ReminderCalendar: the error messages", () => {
  it("refuses a day after the expiry date", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Next month" }));
    await userEvent.click(day(/^Monday, 2 November 2026/));
    expect(screen.getByRole("alert")).toHaveTextContent("Reminders must be on or before the expiry date (31 Oct 2026).");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("refuses a day before the document was issued", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Previous month" }));
    await userEvent.click(day(/^Sunday, 20 September 2026/));
    expect(screen.getByRole("alert")).toHaveTextContent("That's before the document was issued (1 Oct 2026). Pick a day after it.");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("refuses a day that has already passed", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(day(/^Monday, 5 October 2026/));
    expect(screen.getByRole("alert")).toHaveTextContent("That day has already passed, so we couldn't send a reminder then. Pick today or later.");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("refuses a fifth reminder and keeps the four it has", async () => {
    const onChange = vi.fn();
    render(<Harness initial={[20, 14, 7, 1]} onChange={onChange} />);
    await userEvent.click(day(/^Monday, 12 October 2026/));
    expect(screen.getByRole("alert")).toHaveTextContent("You can choose up to 4 reminders. Remove one to pick another.");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("4 of 4 reminders")).toBeInTheDocument();
  });

  it("clears the error after the next valid choice", async () => {
    render(<Harness />);
    await userEvent.click(day(/^Monday, 5 October 2026/));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await userEvent.click(day(/^Saturday, 24 October 2026/));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("still lets old reminders be seen and removed when they are in the past or over the limit", async () => {
    const onChange = vi.fn();
    // Five reminders, one of them 30 days before = 1 Oct, which is before today.
    render(<Harness initial={[30, 20, 14, 7, 1]} onChange={onChange} />);
    expect(screen.getByText("5 of 4 reminders")).toBeInTheDocument();
    expect(screen.getByText(/more than 4/)).toBeInTheDocument();
    expect(screen.getByText(/1 Oct 2026 · 30 days before expiry \(passed\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove the reminder on 1 Oct 2026" }));
    expect(onChange).toHaveBeenLastCalledWith([20, 14, 7, 1]);
  });
});

describe("ReminderCalendar: navigation", () => {
  it("moves between months and jumps to today, the expiry and the issue date", async () => {
    render(<Harness expiryDate="2026-12-20" />);
    await userEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(screen.getByRole("heading", { name: "November 2026" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Expiry date" }));
    expect(screen.getByRole("heading", { name: "December 2026" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous month" }));
    await userEvent.click(screen.getByRole("button", { name: "Issue date" }));
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
  });

  it("follows a new expiry date to its month", () => {
    const { rerender } = render(<Harness />);
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument();
    rerender(<ReminderCalendar {...DOC} issueDate={null} expiryDate="2026-11-20" offsets={[]} onChange={() => undefined} />);
    expect(screen.getByRole("heading", { name: "October 2026" })).toBeInTheDocument(); // today is still in range
  });
});

describe("ReminderCalendar: keyboard", () => {
  it("has a single tab stop and moves with the arrow keys, even across months", async () => {
    render(<Harness />);
    const stops = screen.getAllByRole("button").filter((b) => b.dataset.date && b.tabIndex === 0);
    expect(stops).toHaveLength(1);
    expect(stops[0].dataset.date).toBe("2026-10-09");

    stops[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(document.activeElement).toHaveAttribute("data-date", "2026-10-10");
    await userEvent.keyboard("{ArrowDown}");
    expect(document.activeElement).toHaveAttribute("data-date", "2026-10-17");
    await userEvent.keyboard("{ArrowLeft}{ArrowUp}");
    expect(document.activeElement).toHaveAttribute("data-date", "2026-10-09");
    await userEvent.keyboard("{PageDown}");
    expect(screen.getByRole("heading", { name: "November 2026" })).toBeInTheDocument();
    expect(document.activeElement).toHaveAttribute("data-date", "2026-11-08");
  });

  it("picks a day with Enter and Space", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    day(/^Saturday, 24 October 2026/).focus();
    await userEvent.keyboard("{Enter}");
    expect(onChange).toHaveBeenLastCalledWith([7]);
    await userEvent.keyboard(" ");
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});
