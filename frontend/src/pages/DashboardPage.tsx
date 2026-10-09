import { Link } from "react-router-dom";
import type { Doc, DocumentStatus } from "../api/types";
import { useDashboard, useVehicles } from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { DocumentRow } from "../components/DocumentRow";
import { ErrorNotice } from "../components/ErrorNotice";
import { Spinner } from "../components/Spinner";
import { STATUS_META } from "../lib/status";

const SECTIONS: { key: DocumentStatus; empty: string }[] = [
  { key: "expired", empty: "Nothing has expired. Nice." },
  { key: "expiring_soon", empty: "Nothing is expiring in the next 30 days." },
  { key: "valid", empty: "No other documents yet." },
];

// The home screen: how many documents are in each state, and the documents themselves.
export function DashboardPage() {
  const { user } = useAuth();
  const dashboard = useDashboard();
  const vehicles = useVehicles();

  if (dashboard.isPending) return <Spinner label="Loading your dashboard" />;
  if (dashboard.isError) return <ErrorNotice error={dashboard.error} onRetry={() => dashboard.refetch()} />;

  const data = dashboard.data;
  const firstName = user?.full_name.split(" ")[0];
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Hi{firstName ? `, ${firstName}` : ""}</h1>
          <p className="muted">
            {data.counts.total === 0
              ? "Add your first document and we'll remind you before it expires."
              : needsAttention(data.counts)}
          </p>
        </div>
        <Link className="btn btn-primary" to="/documents?new=1">
          + Add document
        </Link>
      </div>

      <section aria-label="Summary" className="stat-grid">
        {SECTIONS.map(({ key }) => (
          <Link key={key} to={`/documents?status=${key}`} className={`stat stat-${key}`}>
            <span className="stat-number">{data.counts[key]}</span>
            <span className="stat-label">
              <span aria-hidden="true">{STATUS_META[key].icon}</span> {STATUS_META[key].label}
            </span>
          </Link>
        ))}
      </section>

      {data.counts.total === 0 ? (
        <div className="empty">
          <h2>No documents yet</h2>
          <p className="muted">Driver's license, insurance, registration, permits: add anything that expires.</p>
          <Link className="btn btn-primary" to="/documents?new=1">
            Add your first document
          </Link>
        </div>
      ) : (
        SECTIONS.map(({ key, empty }) => {
          const docs: Doc[] = data[key];
          // Hide an empty "valid" group; for the other two an empty state is good news.
          if (docs.length === 0 && key === "valid") return null;
          return (
            <section key={key} className="group" aria-labelledby={`group-${key}`}>
              <h2 id={`group-${key}`}>
                {STATUS_META[key].label} <span className="count">{docs.length}</span>
              </h2>
              {docs.length === 0 ? (
                <p className="muted">{empty}</p>
              ) : (
                <ul className="doc-list">
                  {docs.map((doc) => (
                    <DocumentRow key={doc.id} doc={doc} vehicles={vehicles.data} />
                  ))}
                </ul>
              )}
            </section>
          );
        })
      )}
    </>
  );
}

// One sentence summarising what needs the user's attention.
function needsAttention(counts: { expired: number; expiring_soon: number }): string {
  if (counts.expired > 0) {
    return `${counts.expired} ${counts.expired === 1 ? "document has" : "documents have"} expired. Renew ${counts.expired === 1 ? "it" : "them"} soon.`;
  }
  if (counts.expiring_soon > 0) {
    return `${counts.expiring_soon} ${counts.expiring_soon === 1 ? "document is" : "documents are"} expiring within 30 days.`;
  }
  return "Everything is up to date.";
}
