# Configuration layer — what remains

The self-hosting configuration layer shipped on 2026-11-07 (see
`docs/changelog.md`, correlation `20261107-configuration-layer`, and the
operator guide in [`../configuration.md`](../configuration.md)). Delete this
file once the items below are done.

## Decisions that still bind the remaining work

- Billing is a module: with `billing.mode = "off"` nothing about plans, tiers
  or seats may decide anything.
- Every limit is off until given a number; one key turns on one limit.
- In-app edits are **per-object overrides only** — no instance-wide settings
  editor in the UI. The file is the single source of instance-wide policy.

## Remaining

1. **Browser pass over the billing-off UI.** The Account page's Limits card, the
   department settings without a plan card, the admin-page note, and the
   sign-up page in each mode were type-checked and linted, not exercised in a
   running app.
2. **Stale numbers in older docs.** Some prose still quotes tier numbers as
   if they were universal (e.g. "Free is 3 clusters × 2 topics"); they are now
   the `institution` profile's tier defaults. Fix them as they are touched.
