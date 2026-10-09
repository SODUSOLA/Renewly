// Dates from the API are plain "YYYY-MM-DD" strings with no timezone. Building a
// Date from them directly would shift the day for some users, so we format the
// parts ourselves.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2027-03-01" -> "1 Mar 2027"
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  if (!year || !month || !day) return iso;
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

// "2027-03-01" + 1 year -> "2028-03-01" (used to suggest a renewal date)
export function addYears(iso: string, years: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const d = new Date(Date.UTC(year + years, month - 1, day));
  return d.toISOString().slice(0, 10);
}

// Days-left as a short phrase: "in 12 days", "tomorrow", "today", "3 days ago".
export function describeDaysLeft(daysLeft: number): string {
  if (daysLeft === 0) return "today";
  if (daysLeft === 1) return "tomorrow";
  if (daysLeft === -1) return "yesterday";
  if (daysLeft > 1) return `in ${daysLeft} days`;
  return `${-daysLeft} days ago`;
}

// "15000.5" -> "₦15,000.50" (the API stores money as a decimal string)
export function formatNaira(amount: string): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return amount;
  return `₦${value.toLocaleString("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
