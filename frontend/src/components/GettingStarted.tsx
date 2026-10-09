import { Link } from "react-router-dom";
import type { ChecklistStep, ChecklistSummary } from "../lib/onboarding";

const KIND_NOTE: Record<ChecklistStep["kind"], string> = {
  now: "",
  optional: "Optional",
  later: "When you next renew",
};

// The getting-started checklist: what to do first, what happens on its own later, and how far along
// the user is. Steps tick themselves from real data. It can be hidden and brought back from Settings.
export function GettingStarted({
  summary,
  onDismiss,
  onTour,
}: {
  summary: ChecklistSummary;
  onDismiss: () => void;
  onTour: () => void;
}) {
  const percent = Math.round((summary.done / summary.total) * 100);
  // Emphasise the single most useful next action.
  const nextId = summary.steps.find((s) => !s.done && s.kind === "now")?.id;
  return (
    <section className="card getting-started" aria-labelledby="getting-started-title">
      <div className="getting-started-head">
        <div>
          <h2 id="getting-started-title">{summary.setUp ? "You're all set" : "Get started"}</h2>
          <p className="muted small">
            {summary.setUp
              ? "We'll email you before anything expires. The rest happens naturally as you renew things."
              : "Three quick steps and Renewly is working for you."}
          </p>
        </div>
        <div className="getting-started-actions">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onTour}>
            Take the tour
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onDismiss} aria-label="Hide the getting started checklist">
            Hide
          </button>
        </div>
      </div>

      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={summary.total} aria-valuenow={summary.done} aria-label="Getting started progress">
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="muted small progress-label">
        {summary.done} of {summary.total} done
      </p>

      <ul className="checklist">
        {summary.steps.map((step) => (
          <li key={step.id} className={step.done ? "check-done" : step.id === nextId ? "check-next" : ""}>
            <span className="check-mark" aria-hidden="true">
              {step.done ? "✓" : ""}
            </span>
            <div className="check-text">
              <strong>
                {step.title}
                <span className="sr-only">{step.done ? " (done)" : ""}</span>
              </strong>
              {!step.done && <span className="muted small">{step.description}</span>}
              {!step.done && KIND_NOTE[step.kind] && <span className="check-tag">{KIND_NOTE[step.kind]}</span>}
            </div>
            {!step.done && step.href && (
              <Link className={`btn btn-sm ${step.id === nextId ? "btn-primary" : "btn-ghost"}`} to={step.href}>
                {step.cta}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
