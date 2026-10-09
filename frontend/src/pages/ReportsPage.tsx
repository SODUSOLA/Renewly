import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import type { CostBucket, CostReport } from "../api/types";
import { useCostReport } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Spinner } from "../components/Spinner";
import { MONTH_NAMES, formatDate, formatNaira, percentChange } from "../lib/dates";

// Spending on renewals for a chosen year: totals, by month, by type and by vehicle.
export function ReportsPage() {
  const [year, setYear] = useState<number | undefined>(undefined);
  const report = useCostReport(year);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<unknown>(null);

  if (report.isPending) return <Spinner label="Loading your report" />;
  if (report.isError) return <ErrorNotice error={report.error} onRetry={() => report.refetch()} />;
  const data = report.data;

  // Fetch the CSV with the signed-in token, then hand it to the browser as a file.
  async function download() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const text = await api<string>("/reports/costs.csv", { query: { year: String(data.year) }, as: "text" });
      const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `renewly-renewals-${data.year}.csv`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setDownloadError(error);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Reports</h1>
          <p className="muted">What you've spent keeping your documents valid.</p>
        </div>
        <div className="head-actions">
          <label>
            <span className="sr-only">Year</span>
            <select value={data.year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year">
              {data.available_years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-ghost" onClick={download} disabled={downloading || data.totals.renewals === 0}>
            {downloading ? "Preparing…" : "Download CSV"}
          </button>
        </div>
      </div>
      {downloadError ? <div className="notice notice-error" role="alert">{errorMessage(downloadError)}</div> : null}

      {data.totals.renewals === 0 ? (
        <div className="empty">
          <h2>No renewals in {data.year}</h2>
          <p className="muted">Spending appears here when you mark a document as renewed and enter what you paid.</p>
          <Link className="btn btn-primary" to="/documents">
            Go to your documents
          </Link>
        </div>
      ) : (
        <ReportBody data={data} />
      )}
    </>
  );
}

// Everything below the header, shown when the year has at least one renewal.
function ReportBody({ data }: { data: CostReport }) {
  const { totals } = data;
  const change = percentChange(totals.total, totals.previous_year_total);
  return (
    <>
      <section aria-label="Summary" className="stat-grid">
        <div className="stat stat-valid">
          <span className="stat-number">{formatNaira(totals.total)}</span>
          <span className="stat-label">Spent in {data.year}</span>
          <span className="muted small">{comparison(change, data.year, totals.previous_year_total)}</span>
        </div>
        <div className="stat">
          <span className="stat-number">{totals.renewals}</span>
          <span className="stat-label">{totals.renewals === 1 ? "Renewal" : "Renewals"}</span>
          <span className="muted small">{totals.renewals_with_cost} with a cost recorded</span>
        </div>
        <div className={`stat ${data.missing_cost_count > 0 ? "stat-expiring_soon" : ""}`}>
          <span className="stat-number">{data.missing_cost_count}</span>
          <span className="stat-label">Missing a cost</span>
          <span className="muted small">{data.missing_cost_count > 0 ? "Totals are understated until added" : "Nothing to fill in"}</span>
        </div>
      </section>

      <MonthChart data={data} />

      <div className="two-col">
        <Breakdown title="By type" items={data.by_type} total={totals.total} />
        <Breakdown title="By vehicle" items={data.by_vehicle} total={totals.total} />
      </div>

      {data.missing_cost.length > 0 && (
        <section className="group" aria-labelledby="missing">
          <h2 id="missing">
            Add the cost <span className="count">{data.missing_cost_count}</span>
          </h2>
          <p className="muted small">Open a document and choose “Add cost” on its renewal history.</p>
          <ul className="doc-list">
            {data.missing_cost.map((m) => (
              <li key={m.renewal_id}>
                <Link to={`/documents/${m.document_id}`} className="doc-row">
                  <span className="doc-title">{m.title}</span>
                  <span className="muted small">renewed {formatDate(m.renewed_on)}</span>
                </Link>
              </li>
            ))}
          </ul>
          {data.missing_cost_count > data.missing_cost.length && (
            <p className="muted small">…and {data.missing_cost_count - data.missing_cost.length} more.</p>
          )}
        </section>
      )}
    </>
  );
}

// "↑ 87% more than 2025" / "↓ 20% less than 2025" / "Nothing recorded in 2025".
function comparison(change: number | null, year: number, previousTotal: string): string {
  if (change === null) return `Nothing recorded in ${year - 1}`;
  if (change === 0) return `Same as ${year - 1} (${formatNaira(previousTotal)})`;
  return `${change > 0 ? "↑" : "↓"} ${Math.abs(change)}% ${change > 0 ? "more" : "less"} than ${year - 1} (${formatNaira(previousTotal)})`;
}

// Twelve bars, one per month. The picture is decorative; the label gives screen readers the numbers.
function MonthChart({ data }: { data: CostReport }) {
  const max = Math.max(...data.by_month.map((m) => Number(m.total)), 0);
  const summary = data.by_month.map((m) => `${MONTH_NAMES[m.month - 1]} ${formatNaira(m.total)}`).join(", ");
  return (
    <section className="group" aria-labelledby="by-month">
      <h2 id="by-month">Spending by month</h2>
      <div className="chart card" role="img" aria-label={`Spending by month in ${data.year}: ${summary}`}>
        {data.by_month.map((m) => {
          const height = max > 0 ? (Number(m.total) / max) * 100 : 0;
          return (
            <div key={m.month} className="chart-col" title={`${MONTH_NAMES[m.month - 1]}: ${formatNaira(m.total)}`}>
              <span className="chart-value" aria-hidden="true">
                {Number(m.total) > 0 ? compact(m.total) : ""}
              </span>
              <span className="chart-bar" aria-hidden="true" style={{ height: `${Math.max(height, Number(m.total) > 0 ? 3 : 0)}%` }} />
              <span className="chart-label" aria-hidden="true">
                {MONTH_NAMES[m.month - 1].slice(0, 3)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// 150000.5 -> "150k", 1250000 -> "1.3M": short enough to sit above a bar.
function compact(amount: string): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(Number(amount));
}

// A ranked list of categories, each with its share of the year's total.
function Breakdown({ title, items, total }: { title: string; items: CostBucket[]; total: string }) {
  const sum = Number(total);
  return (
    <section className="group" aria-label={title}>
      <h2>{title}</h2>
      <ul className="breakdown card">
        {items.map((item) => {
          const share = sum > 0 ? (Number(item.total) / sum) * 100 : 0;
          return (
            <li key={item.label}>
              <div className="breakdown-row">
                <span>{item.label}</span>
                <strong>{formatNaira(item.total)}</strong>
              </div>
              <div className="share" aria-hidden="true">
                <span style={{ width: `${share}%` }} />
              </div>
              <span className="muted small">
                {item.renewals} {item.renewals === 1 ? "renewal" : "renewals"} · {Math.round(share)}%
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
