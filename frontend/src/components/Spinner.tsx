// A loading indicator. `fullPage` centres it for whole-screen waits.
export function Spinner({ label = "Loading", fullPage = false }: { label?: string; fullPage?: boolean }) {
  return (
    <div className={fullPage ? "spinner-page" : "spinner-inline"} role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
