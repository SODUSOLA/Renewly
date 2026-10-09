// Reminder offsets are edited as text ("90, 30, 14, 7, 1") and sent as numbers.

export const DEFAULT_OFFSETS = [90, 30, 14, 7, 1];
export const MAX_OFFSET_DAYS = 365;
export const MAX_OFFSETS = 10;

export type OffsetParse = { ok: true; value: number[] } | { ok: false; error: string };

// Parses "90, 30 14" into [90, 30, 14] (largest first, no duplicates). An empty
// string is valid and means "no reminders".
export function parseOffsets(text: string): OffsetParse {
  const parts = text.split(/[\s,]+/).filter(Boolean);
  const numbers: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return { ok: false, error: `"${part}" is not a whole number of days.` };
    numbers.push(Number(part));
  }
  const unique = [...new Set(numbers)].sort((a, b) => b - a);
  if (unique.length > MAX_OFFSETS) return { ok: false, error: `Use at most ${MAX_OFFSETS} reminders.` };
  if (unique.some((n) => n > MAX_OFFSET_DAYS)) {
    return { ok: false, error: `Reminders can be at most ${MAX_OFFSET_DAYS} days before expiry.` };
  }
  return { ok: true, value: unique };
}

export function offsetsToText(offsets: number[]): string {
  return offsets.join(", ");
}
