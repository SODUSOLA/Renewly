// Timezone choices for sign-up. The browser knows the full IANA list.

const FALLBACK = ["Africa/Lagos", "Africa/Nairobi", "Africa/Johannesburg", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Dubai", "Asia/Kolkata", "UTC"];

// The visitor's own timezone, or Lagos if the browser won't say.
export function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Lagos";
  } catch {
    return "Africa/Lagos";
  }
}

// Every timezone the browser knows (always including `selected`).
export function timezoneOptions(selected: string): string[] {
  let all: string[] = [];
  try {
    all = Intl.supportedValuesOf("timeZone");
  } catch {
    all = FALLBACK;
  }
  return all.includes(selected) ? all : [selected, ...all];
}
