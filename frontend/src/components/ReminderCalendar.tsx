import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { formatDate } from "../lib/dates";
import {
  MAX_REMINDERS,
  addDays,
  addMonths,
  describeOffset,
  diffDays,
  earliestReminderDate,
  longDate,
  monthGrid,
  monthOf,
  monthTitle,
  toggleReminder,
} from "../lib/calendar";

const WEEKDAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  issueDate: string | null;
  expiryDate: string;
  today: string;
  // Reminders chosen so far, as days before expiry (largest first).
  offsets: number[];
  onChange: (offsets: number[]) => void;
}

// The month a person most likely wants to see first: today if the document is still valid,
// otherwise the expiry month (which can be in the past for an overdue document).
function startMonth(today: string, issueDate: string | null, expiryDate: string): string {
  const base = issueDate && issueDate > today ? issueDate : today;
  return monthOf(base > expiryDate ? expiryDate : base);
}

// A month calendar for choosing reminder days. It shows the issue date, the expiry date and
// today, shades the days a reminder is allowed on, and explains in words when a click is
// refused (after expiry, before issue, in the past, or beyond the limit).
export function ReminderCalendar({ issueDate, expiryDate, today, offsets, onChange }: Props) {
  const [month, setMonth] = useState(() => startMonth(today, issueDate, expiryDate));
  const [focused, setFocused] = useState<string>(() => addDays(expiryDate, -(offsets[0] ?? 0)));
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  const shouldFocus = useRef(false);

  // When the expiry date is edited, show the month where the choosing happens.
  useEffect(() => {
    setMonth(startMonth(today, issueDate, expiryDate));
    setFocused(today > expiryDate ? expiryDate : today);
    setNotice(null);
    // Only a new expiry date restarts the view; other prop changes must not yank the month away.
  }, [expiryDate]);

  // Move the keyboard focus to the chosen day after the grid re-renders.
  useEffect(() => {
    if (!shouldFocus.current) return;
    shouldFocus.current = false;
    grid.current?.querySelector<HTMLButtonElement>(`[data-date="${focused}"]`)?.focus();
  }, [focused, month]);

  const earliest = earliestReminderDate({ issueDate, expiryDate, today });
  const chosen = new Set(offsets.map((o) => addDays(expiryDate, -o)));
  const ctx = { issueDate, expiryDate, today, offsets };

  function choose(date: string) {
    const result = toggleReminder(date, ctx);
    setNotice({ text: result.message, error: !result.ok });
    setFocused(date);
    if (result.ok) onChange(result.offsets);
  }

  // Arrow keys move between days, PageUp/PageDown between months, like a native date picker.
  function onKeyDown(event: KeyboardEvent) {
    const steps: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    let next: string | null = null;
    if (event.key in steps) next = addDays(focused, steps[event.key]);
    else if (event.key === "PageUp") next = addDays(focused, -30);
    else if (event.key === "PageDown") next = addDays(focused, 30);
    if (!next) return;
    event.preventDefault();
    shouldFocus.current = true;
    setFocused(next);
    setMonth(monthOf(next));
  }

  const rows = monthGrid(month);
  const focusableDate = monthOf(focused) === month ? focused : `${month}-01`;
  const sortedChosen = [...offsets].sort((a, b) => a - b); // soonest reminder first in the list

  return (
    <div className="calendar card">
      <div className="calendar-head">
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Previous month" onClick={() => setMonth(addMonths(month, -1))}>
          ‹
        </button>
        <h3 aria-live="polite">{monthTitle(month)}</h3>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Next month" onClick={() => setMonth(addMonths(month, 1))}>
          ›
        </button>
      </div>

      <div className="calendar-jump">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMonth(monthOf(today))}>
          Today
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMonth(monthOf(expiryDate))}>
          Expiry date
        </button>
        {issueDate && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMonth(monthOf(issueDate))}>
            Issue date
          </button>
        )}
      </div>

      <div className="calendar-grid" role="grid" aria-label={`Choose reminder days, ${monthTitle(month)}`} ref={grid} onKeyDown={onKeyDown}>
        <div className="calendar-row" role="row">
          {WEEKDAY_HEADERS.map((name) => (
            <span key={name} className="calendar-weekday" role="columnheader">
              {name}
            </span>
          ))}
        </div>
        {rows.map((week, i) => (
          <div className="calendar-row" role="row" key={i}>
            {week.map((date, j) =>
              date === null ? (
                <span key={j} className="calendar-pad" role="gridcell" />
              ) : (
                <span key={date} role="gridcell">
                  <DayButton
                    date={date}
                    state={{
                      selected: chosen.has(date),
                      past: chosen.has(date) && date < today,
                      issued: date === issueDate,
                      expiry: date === expiryDate,
                      today: date === today,
                      allowed: date >= earliest && date <= expiryDate,
                    }}
                    expiryDate={expiryDate}
                    tabbable={date === focusableDate}
                    onChoose={choose}
                  />
                </span>
              ),
            )}
          </div>
        ))}
      </div>

      <ul className="calendar-legend" aria-label="Legend">
        <li><span className="swatch swatch-selected" /> Reminder</li>
        <li><span className="swatch swatch-expiry" /> Expires</li>
        {issueDate && <li><span className="swatch swatch-issued" /> Issued</li>}
        <li><span className="swatch swatch-allowed" /> You can pick</li>
      </ul>

      <p className={notice?.error ? "calendar-note calendar-note-error" : "calendar-note"} role={notice?.error ? "alert" : "status"}>
        {notice?.text ?? `Click a day to add a reminder. You can choose up to ${MAX_REMINDERS}, between ${formatDate(earliest)} and ${formatDate(expiryDate)}.`}
      </p>

      <div className="reminder-summary">
        <strong>
          {offsets.length} of {MAX_REMINDERS} reminders
        </strong>
        {offsets.length > MAX_REMINDERS && (
          <span className="muted small"> This document has more than {MAX_REMINDERS}. You can keep them or remove some.</span>
        )}
        {offsets.length === 0 ? (
          <p className="muted small">No reminders: you won't be emailed about this document.</p>
        ) : (
          <ul className="chips">
            {sortedChosen.map((offset) => {
              const date = addDays(expiryDate, -offset);
              return (
                <li key={offset} className={`chip${date < today ? " chip-past" : ""}`}>
                  <span>
                    {formatDate(date)} · {describeOffset(offset)}
                    {date < today ? " (passed)" : ""}
                  </span>
                  <button type="button" aria-label={`Remove the reminder on ${formatDate(date)}`} onClick={() => choose(date)}>
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {offsets.length > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { onChange([]); setNotice({ text: "Cleared all reminders.", error: false }); }}>
            Clear all
          </button>
        )}
      </div>
    </div>
  );
}

interface DayState {
  selected: boolean;
  past: boolean;
  issued: boolean;
  expiry: boolean;
  today: boolean;
  allowed: boolean;
}

// One day on the calendar. Not disabled when it can't be chosen: clicking it explains why.
function DayButton({ date, state, expiryDate, tabbable, onChoose }: { date: string; state: DayState; expiryDate: string; tabbable: boolean; onChoose: (date: string) => void }) {
  const classes = ["day"];
  if (state.allowed) classes.push("day-allowed");
  else classes.push("day-blocked");
  if (state.selected) classes.push("day-selected");
  if (state.expiry) classes.push("day-expiry");
  if (state.issued) classes.push("day-issued");
  if (state.today) classes.push("day-today");

  const facts = [];
  if (state.expiry) facts.push("Expiry date");
  if (state.issued) facts.push("Issue date");
  if (state.today) facts.push("Today");
  if (state.selected) facts.push(`Reminder, ${describeOffset(diffDays(expiryDate, date))}${state.past ? ", already passed" : ""}`);
  else if (!state.allowed) facts.push("Not available for a reminder");
  const marker = state.expiry ? "Expires" : state.issued ? "Issued" : state.selected ? "✓" : state.today ? "Today" : "";

  return (
    <button
      type="button"
      className={classes.join(" ")}
      data-date={date}
      tabIndex={tabbable ? 0 : -1}
      aria-pressed={state.selected}
      aria-label={`${longDate(date)}${facts.length ? `. ${facts.join(". ")}` : ""}`}
      onClick={() => onChoose(date)}
    >
      <span className="day-number">{Number(date.slice(8))}</span>
      <span className="day-marker" aria-hidden="true">
        {marker}
      </span>
    </button>
  );
}
