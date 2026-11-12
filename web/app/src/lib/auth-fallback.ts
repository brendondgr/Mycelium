/**
 * The native-submit target of an auth form.
 *
 * The forms are submitted by JavaScript (`fetch` to the API). If a browser
 * submits one natively anyway (scripts blocked or failed to load), the form's
 * `method="post"` keeps the credentials out of the URL, browser history and
 * access logs, and this handler throws the body away unread. A 303 turns the
 * reply into a plain GET of the form page, so reloading does not ask to resend
 * form data. The `Location` is relative on purpose: behind Nginx, the request
 * URL Next sees carries the container's host, not the one the browser used.
 */
export function authFallback(page: string): Response {
  return new Response(null, {
    status: 303,
    headers: { Location: `${page}?nojs=1`, "Cache-Control": "no-store" },
  });
}
