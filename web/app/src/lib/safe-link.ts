/**
 * The link schemes any renderer of untrusted text (Mylo's answers, the report
 * body) may make clickable. Everything else — `javascript:`, `data:`, `vbscript:`
 * — is shown as text, never as an `href`.
 */
export const SAFE_LINK = /^(https?:\/\/|mailto:)/i;

/** Whether `url` may become an `href`. */
export function isSafeLink(url: string | null | undefined): url is string {
  return typeof url === "string" && SAFE_LINK.test(url.trim());
}
