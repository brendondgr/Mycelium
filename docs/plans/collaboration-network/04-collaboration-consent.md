# Plan CN-04 — Collaboration Consent

**Status:** draft. **Depends on:** CN-01, CN-02. **Unblocks:** CN-05.
**Correlation ID:** `20260918-collaboration-network-04`

## Objective

Before anyone can be found, the person decides whether they can be, by whom,
for what, and until when — and sees exactly what a seeker would see
(`design §7`). Separate "who can find me" (the candidate's, set once) from
"where I want to look" (the seeker's, per search).

## The setting

1. **`CollaborationSetting`** (per user, in `apps/collab`):
   - `open` — default **off**. Absent row means off.
   - `audience` ∈ {`institution`, `country`, `anywhere`}, default
     `institution`.
   - `open_to` — any of {`co_authoring`, `grant_partner`, `data_sharing`,
     `mentoring`}; used as a filter and a label only (OD-CN4).
   - `expires_at` — default six months from turning on
     (`COLLAB_OPEN_MONTHS`). Fourteen days before, a bell notification and,
     for linked accounts, a Mylo DM ask to renew. On expiry `open` turns off
     by itself.
2. Turning it off removes the person from every result immediately; there is
   no cache of candidates that outlives the switch.

## Verified scope

3. **`VerifiedAffiliation`** (per user): the institution and country derived
   from the person's **verified** email domain against the affiliation
   directory's domains. The directory currently lives only at
   `web/app/public/data/institutions.json`; this plan gives the backend a read
   of the same file (one source, built by `npm run institutions`) rather than
   a copy.
4. A person whose verified email matches no institution (a personal address)
   has no verified institution: they can choose `anywhere` or nothing, and
   they cannot search at `institution` scope. `Profile.institution`, which is
   free text, is never used for scope.
5. Scope applies to both sides: a seeker's search scope is also resolved from
   their own verified affiliation.

## Preview and copy

6. **Preview.** The Settings tab shows the exact coarse pointer (`design
   §9.4`) a seeker would see: name, verified affiliation, and for each facet
   the concepts a search could match on with their tier ("from your profile",
   "from your papers"). Conversational edges are never listed, because they
   can never match (README tier table), and the preview says so.
7. **Honest copy**, in these words or close to them: "Choosing who can find
   you limits where you appear. It does not guarantee who sees you. Anyone in
   your audience who searches for what you work on may see your name,
   affiliation, and the topic that matched. People are never told someone
   searched for them, and neither are you."

## Appearance cap

8. **`Appearance`** ledger: (candidate, seeker, ISO week). A candidate is shown
   to at most `COLLAB_APPEARANCE_CAP` distinct seekers per week (default 10);
   a seeker who has already seen them this week keeps seeing them. Rows older
   than eight weeks are deleted. The ledger is never shown to the candidate
   (`design §9.3`) and never to the seeker.

## Who may do what

9. Per OD-CN5 (recommendation): any **verified** account may turn `open` on;
   searching outside one's own lab requires a paid effective tier, resolved
   exactly as other caps are (`apps/billing/entitlements.py`).

## Steps

10. Models, migrations, the directory read, the affiliation resolver.
11. API: `GET/PUT /api/collab/settings/`, `GET /api/collab/preview/`.
12. The Settings tab ("Collaboration") in the profile settings, with the
    preview and the copy; mobile-first per `docs/styles.md`.
13. Expiry task and renewal notification.
14. Tests; changelog; repo map; `docs/api-contract.md`.

## Acceptance

- A user with no `CollaborationSetting` row is not a candidate anywhere.
- A free-text institution that disagrees with the verified domain has no effect.
- An expired setting reads as off without a job having run.
- The preview lists no conversational edge and no project edge.
- No response body of any endpoint in this app contains another user's
  appearance count.

## Open decisions

- **OD-CN04a** Default audience. Recommendation: `institution`, the narrowest.
- **OD-CN04b** Whether a lab's PI can see which members are open.
  Recommendation: no; it is each person's own choice and seeing it invites
  pressure.

## Sandbox validation (before moving on)

Extends the world with a **consent matrix**: a planted share of people opt in,
with audiences spread over institution, country and anywhere, some already
expired, and some on personal email domains that match no institution.

- **Verified scope** derived for every person matches the planted institution
  and country exactly (accuracy 1.0); personal-domain people have none.
- **Preview** for every opted-in person lists no conversational and no project
  edge (invariant), and every concept it lists is one a search could match.
- **Expiry** reads as off at query time with no job run (invariant).
- **Appearance ledger** under a simulated week of searches: no candidate
  exceeds the cap for new seekers (invariant).

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every default value and setting name, and what is deliberately not
being done. A deviation discovered mid-implementation stops the work and reopens
the brief.
