import { Modal } from "./Modal";

// The first thing a brand-new user sees: what the app does in three lines, and a choice between
// a one-minute tour and getting on with it. Closing it counts as "skip".
export function WelcomeDialog({ firstName, onTour, onSkip }: { firstName?: string; onTour: () => void; onSkip: () => void }) {
  return (
    <Modal title={firstName ? `Welcome, ${firstName}` : "Welcome to Renewly"} onClose={onSkip}>
      <p className="lead">Never be caught out by an expired licence, insurance or permit again.</p>
      <ol className="welcome-steps">
        <li>
          <span className="welcome-number" aria-hidden="true">1</span>
          <span>
            <strong>Add a document</strong>
            <span className="muted small">with its expiry date.</span>
          </span>
        </li>
        <li>
          <span className="welcome-number" aria-hidden="true">2</span>
          <span>
            <strong>Pick your reminder days</strong>
            <span className="muted small">and we'll email you before it expires.</span>
          </span>
        </li>
        <li>
          <span className="welcome-number" aria-hidden="true">3</span>
          <span>
            <strong>Renew it, then mark it as renewed</strong>
            <span className="muted small">and we start watching the new date.</span>
          </span>
        </li>
      </ol>
      <div className="actions">
        <button type="button" className="btn btn-ghost" onClick={onSkip}>
          Skip, I'll explore
        </button>
        <button type="button" className="btn btn-primary" onClick={onTour}>
          Take a 1-minute tour
        </button>
      </div>
    </Modal>
  );
}
