export const WEEKDAYS = [
  { number: 1, label: "Thứ 2" },
  { number: 2, label: "Thứ 3" },
  { number: 3, label: "Thứ 4" },
  { number: 4, label: "Thứ 5" },
  { number: 5, label: "Thứ 6" },
  { number: 6, label: "Thứ 7" },
];

export const SESSIONS = [
  { value: "morning", label: "Sáng" },
  { value: "afternoon", label: "Chiều" },
] as const;

/** "07:00:00" to "07:00". */
export function hhmm(time: string): string {
  return time.slice(0, 5);
}

/** Morning before afternoon, then by number. */
export function inSchoolOrder<T extends { session: string; number: number }>(periods: T[]): T[] {
  const rank = (p: T) => (p.session === "morning" ? 0 : 1) * 10 + p.number;
  return [...periods].sort((a, b) => rank(a) - rank(b));
}

export function periodName(period: { session: string; number: number }): string {
  const session = SESSIONS.find((s) => s.value === period.session)?.label ?? period.session;
  return `${session} ${period.number}`;
}

/** Whether `now` (local time) falls inside the period's clock times. */
export function isCurrent(period: { starts_at: string; ends_at: string }, now: Date): boolean {
  const time = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  return hhmm(period.starts_at) <= time && time < hhmm(period.ends_at);
}
