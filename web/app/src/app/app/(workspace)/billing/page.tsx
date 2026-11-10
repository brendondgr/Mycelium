import { appRedirect } from "@/lib/auth-server";

/**
 * Billing folded into the Account page — plans are now its Subscription
 * management half. The old route stays as a redirect because it is in people's
 * history and bookmarks, and a 404 is a worse answer than the page they wanted.
 */
export default async function BillingPage() {
  await appRedirect("/app/account");
}
