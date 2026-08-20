/**
 * Date formatting shared by the feed cards.
 *
 * Lives in `lib/` rather than beside the cards that use it because the deadline
 * control and the card tool bar each need it and each import the other's
 * module — a cycle that a leaf utility module simply removes.
 */

/**
 * Format a date-only `YYYY-MM-DD` string as "Nov 12, 2026", in local time.
 *
 * `new Date("2026-09-10")` is **not** what you want here. ECMAScript reads the
 * date-only form as UTC midnight, so every timezone behind UTC renders the day
 * before: in America/New_York that exact string prints "Sep 9, 2026". A
 * deadline shown a day early is the worst direction for this product to be
 * wrong in — the whole corpus is deadlines, and a reader who trusts the card
 * submits late.
 *
 * Splitting the parts and going through the local-time `Date(y, m, d)`
 * constructor keeps the calendar date the backend sent. The backend sends a
 * plain calendar date on purpose: a funder's "due Nov 12" is a calendar day in
 * the funder's own world, not an instant, and re-projecting it through the
 * reader's timezone invents precision nobody wrote down.
 *
 * Use this for `deadline_date`, `posted`, `due_dates[]` and friends. For a real
 * instant (`2026-09-10T11:59:00Z`, e.g. a conference round's `instant`), plain
 * `new Date(...)` is correct and this would throw the time away.
 */
export function formatIsoDate(dateIso: string): string {
  if (!dateIso) return "";
  const [y, m, d] = dateIso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return dateIso;
  const date = new Date(y, m - 1, d);
  if (Number.isNaN(date.getTime())) return dateIso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
