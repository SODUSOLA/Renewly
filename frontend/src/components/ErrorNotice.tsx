import { ApiError, errorMessage } from "../api/client";

// Shows an error in plain words. The request id is shown for server faults so
// a user can quote it when reporting a problem.
export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const requestId = error instanceof ApiError && error.status >= 500 ? error.requestId : null;
  return (
    <div className="notice notice-error" role="alert">
      <p>{errorMessage(error)}</p>
      {requestId && <p className="muted small">Reference: {requestId}</p>}
      {onRetry && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
