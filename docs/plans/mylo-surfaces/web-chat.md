# Plan W: Mylo chat in the web app

Index, owner decisions and sequencing: [README.md](README.md). Depends on the
shared contract (track S) in that file.

**Status.** Written against the reworked workspace as it stands on `main`
(`6b37f03`: the shared feed card, item detail, toolbar and reader layout). The
entry points and file placement are fixed here. Visual detail (exact sizes,
motion, copy) is settled while building W2, in the browser, under
`docs/styles.md`.

## Objective

A person can ask Mylo about any one thing by pressing a small button with
Mylo's face on it, and can talk to Mylo in general from anywhere in the app.
Either way a side panel opens. It shows the answer and what Mylo is doing to
get there, never Mylo's reasoning (S-9). It is the same agent, gate and event
log that Discord uses.

## What exists

- Every route the panel needs is live under `api/tools/agent/` (status,
  catalog, threads, messages, the event stream, answer, cancel, fork, export,
  reference search, preferences, policy). Nothing in the web app calls them
  yet.
- The web app has no stream consumer. Data goes through
  `@tanstack/react-query` and `lib/portal/{client,hooks,mutations}.ts`, with
  the `mycelium_csrftoken` cookie sent as `X-CSRFToken`.
- Every feed draws its items with `FeedCard` and `ItemDetail`
  (`components/portal/feed/parts.tsx`). `FeedCard` has an `actions` slot at
  the top right (remind, save, ignore) and `ItemDetail` has a matching `tools`
  slot. The slots are filled in two places: `feed/opportunity-feed.tsx`
  (grants, fellowships, conferences) and
  `sections/research-papers-section.tsx` (papers).
- The reader layout (`feed/reader.tsx`) pins the opened item beside the list
  at 980 px and wider, and slides it in as a drawer below that. Overlays are
  drawn through its `Portal` at the end of `<body>`.
- App-wide hosts are mounted in `components/portal/workspace-shell.tsx`
  (`CollaboratorSearchHost` is the precedent: mounted once, opened by a window
  event from anywhere).
- Mylo's painted head is already on cards as a small decorative mark beside
  "Mylo's reason" (`MyloMark` in `feed/parts.tsx`, from
  `public/mylo-portrait-64.webp`). The SVG rig is not used.

## Two ways in

### 1. The Mylo-face button on a thing (S-15)

A small round button showing Mylo's painted head. Pressing it opens the side
panel on a conversation about that thing.

| Where | Slot | Anchor |
| --- | --- | --- |
| Every feed card (papers, grants, fellowships, conferences) | first in `FeedCard.actions`, before remind / save / ignore | `item` + content id |
| The opened item | first in `ItemDetail.tools` | the same |
| A project page | in its `PageHead`, beside the title | `project` |
| A lab or department overview | in its `PageHead` | `lab` / `department` |

Rules for the button:

- One component, `AskMyloButton`, used everywhere. It sends the window event
  `mycelium:ask-mylo` with `{anchor, title}`; it knows nothing about the
  panel.
- It must not be mistaken for the decorative mark that already sits beside
  "Mylo's reason". It is a real button: a ring around the head, the same
  30 px hit area as its neighbours, a visible focus ring, the name
  "Ask Mylo about <title>" for assistive technology and "Ask Mylo" as its
  tooltip.
- On a card the other actions fade until the card is hovered. Mylo's face
  stays at full strength so it reads as the way in.
- Pressing it does not open or change the reader's selected item
  (`?item=` is untouched).
- Pressing it again on the same thing reopens the conversation already open
  about it; it does not start a second one. A conversation is stored only
  when the first question is sent, so opening and closing the panel leaves
  nothing in history.

### 2. The launcher

Mylo's painted head, fixed at the bottom right of every signed-in page. It
opens the panel on the last conversation, or a new general one. On a project,
lab or department page a new conversation starts in that scope. It is hidden
while the panel is open.

Both ways open the same panel. Only one panel exists.

## The panel

Structure after the Claude Code side panel; the turn display after GAIFA's
chat.

```
┌──────────────────────────────────────────┐
│ ◉ Title of this chat        ⟲   ＋   ⚲  ✕ │   history · new chat · pin · close
│   About: NSF CAREER 2027 (if anchored)   │
├──────────────────────────────────────────┤
│  You                                     │
│  Is my lab eligible for this?            │
│                                          │
│  ◌ Reading the call…                     │   one activity line per turn,
│    ✓ Looked at your lab's projects       │   opens to the list of steps
│    ✓ Read the eligibility section        │
│                                          │
│  Mylo                                    │
│  Yes, with one condition … [1] [2]       │   citation pills open the item
│                                          │
├──────────────────────────────────────────┤
│  Ask Mylo…                          ➤    │   Enter sends · Shift+Enter newline
│  Local model · runs on this machine      │
└──────────────────────────────────────────┘
```

- **Placement.** A drawer on the right edge, drawn through `Portal`. At 980 px
  and wider it is not modal: it lies over the reading pane, the list stays
  usable, and pressing another card's Mylo button switches the conversation.
  Below that it is a full-screen sheet with a trapped focus, like the item
  drawer.
- **Header.** The conversation's title (set by the agent after the first
  answer, editable). Three icons (S-8): history, new chat, pin. No per-answer
  bookmarks. An anchored conversation names its thing on a second line, as a
  link that opens it in the reader.
- **Activity, not thinking.** Each turn has one fold. While Mylo works, its
  header shows the current step with a quiet shimmer ("Reading the call…").
  Opened, it lists the steps taken with a tick or a cross. Labels come from
  the server's activity view (S1); the panel has no label table of its own
  and never receives reasoning text. When the answer arrives the fold
  collapses to "Looked at 3 things".
- **Answer.** Streams in as text. Citations are small numbered pills that open
  the item in the reader. No scores, percentages or verdicts
  (`docs/styles.md`).
- **Questions from Mylo.** A small dock above the composer with the options;
  the composer is the free-text answer.
- **Composer.** Enter sends, Shift+Enter makes a new line. While Mylo is
  working, a new message waits its turn and shows as queued; a Stop button
  replaces Send. `@` opens reference search to attach an item or project.
- **Where it runs.** One line under the composer names the model and whether
  it runs on this machine (S-3), from `GET api/tools/agent/status/`.
- **History.** Replaces the conversation with a searchable list: pinned first,
  then recent; rename, pin, archive, delete from the row.
- **Mylo's head** is the avatar beside the activity line. It may use the
  existing gentle float while Mylo is working and stays still when the person
  prefers reduced motion.

## States every view must have

| State | What shows |
| --- | --- |
| Loading | Skeleton rows for the conversation; the composer is usable at once |
| Empty | A greeting and three starter questions fitted to the anchor (item, project, lab) or general |
| Working | The activity line; Stop |
| Waiting on the person | The question dock |
| Error in a turn | The error in plain words with "Try again"; the conversation is kept |
| Connection lost | A thin "Reconnecting…" bar; the stream resumes from the last event with no duplicates |
| Not allowed | Why, and where to change it: chat turned off in *Mylo & you*, plan does not include it, email not verified, no model configured |
| Stale | A conversation changed in another tab reloads its tail on focus |

When chat is not available to the person, the Mylo-face buttons are not drawn
and the launcher opens the "Not allowed" state, so the reason is said once and
not on every card.

Accessibility: the panel is a labelled complementary region; focus moves to
the composer on open and back to the button that opened it on close; Escape
closes; the activity line is a polite live region that announces a step once,
not every token; targets and contrast meet WCAG 2.2 AA in both themes.

## What it needs from the backend

The routes that exist, plus track S:

| Need | Source |
| --- | --- |
| Steps without thinking | S1: the stream and events routes default to `view=activity` |
| "Ask about this", and finding the conversation already open about it | S2: `POST threads/` accepts `anchor`; `GET threads/` filters by it |
| Pin | S3: `PATCH threads/<id>/` accepts `pinned`; the list orders pinned first |
| Model line | S3: `status/` returns `model {name, label, location}` |

## Phases

All web commands run in `web/app`. Read the relevant pages of
`node_modules/next/dist/docs/` before writing code (`web/CLAUDE.md`).

### W1. Data layer and stream client (needs track S only)

No visible UI. New `web/app/src/lib/portal/agent/` (`types.ts`, `client.ts`,
`stream.ts`, `turns.ts`), with hooks beside the others in
`lib/portal/hooks.ts` and `mutations.ts`.

- Queries and mutations for status, threads (with the anchor filter), one
  thread's events, send, answer, cancel, rename, pin, archive, preferences.
- A stream client. The stream is a same-origin GET with the session cookie,
  so the browser's `EventSource` and a `fetch` reader both work; pick one
  after reading the Next.js docs. It replays from `Last-Event-ID`, drops
  events whose sequence number it has already applied, and reconnects with a
  capped backoff.
- A reducer that turns the event stream into the turn model the panel draws:
  question, activity steps, answer text, question dock, error.
- A check that neither the dev proxy nor nginx buffers the stream. A buffered
  stream shows nothing until the turn ends. (The route already sends
  `X-Accel-Buffering: no`. `stream/` and `events/` are registered with the
  trailing slash only, which the dev proxy strips; confirm the GET still
  resolves, and register the second form if it does not.)

`web/app` has no unit-test runner today (`package.json` has `lint` and `build`
only). W1 adds one as a dev dependency with an `npm test` script, used for
pure functions only.

```bash
npm test && npm run lint && npm run build
curl -N -b "$COOKIES" http://localhost:11050/api/tools/agent/threads/<id>/stream/
```

Accept when a recorded three-step turn replays into the same turn model
whether delivered whole, in two halves across a reconnect, or with duplicated
events; and the `curl` shows events arriving while a turn runs.

### W2. The panel and the launcher

New `web/app/src/components/portal/mylo/`: `chat-host.tsx` (mounted in
`workspace-shell.tsx` beside `CollaboratorSearchHost`; listens for
`mycelium:ask-mylo`), `chat-panel.tsx`, `turn.tsx`, `activity-fold.tsx`,
`composer.tsx`, `question-dock.tsx`, `launcher.tsx`. Styles join
`components/portal/workspace.css` under the `ws-` prefix.

```bash
npm run lint && npm run build
```

Then in the browser against the running stack (`localhost:11050`), reading the
DOM, not only screenshots: a general question end to end; every row of the
states table forced once; 375 px and 1280 px; both themes; reduced motion;
keyboard only. Accept when no reasoning text is present in the DOM at any
point of a turn that used thinking, and a dropped connection resumes without a
repeated or missing step.

### W3. The Mylo-face button

`components/portal/mylo/ask-button.tsx`; wired into the `actions` and `tools`
slots in `feed/opportunity-feed.tsx` and
`sections/research-papers-section.tsx`, and into the page heads of the
project, lab and department views. The anchored header line in the panel.

Accept when: the button is on every card and opened item of all four feeds;
pressing it opens a conversation whose first turn has the thing as `#1`
without the person naming it; pressing it twice gives one conversation;
opening and closing without asking stores nothing; the reader's selection does
not change; the button is absent for a person who may not chat.

### W4. History and pin

The list view in the panel: search, rename, pin, archive, delete.

Accept when a pinned conversation stays first across reloads and an archived
one leaves the list and returns under "Archived".

### W5. Settings

Chat on or off and what Mylo may learn from chats, in *Mylo & you*
(`/app/mylo-and-you`); the lab's or department's narrowing policy in its
settings pages. The preference and policy routes already exist. Once plan D's
first phase has landed, the policy page also shows the Discord guest level
(`full`, `no_people`, `public`, `off`; S-16) with one sentence on what each
gives someone without an account, and the host's ceiling when it is lower.

### Docs, in the phase that lands the code

`docs/repo-map.md` (the two new folders), `docs/styles.md` (the Mylo-face
button and the panel as patterns), `docs/changelog.md`.

## Rules

- The panel renders the server's activity view. It never requests the raw
  view and has no code path that could show reasoning text.
- The web holds no permission logic. What a person may ask about, and what
  Mylo may read for them, is decided by the agent's gate; the panel shows the
  refusal it is given.
- Tier gate: the existing `agent` entitlement through `billing.entitlements`
  (the app already reads entitlements with `useEntitlements`).
- Conversations are private to their owner. Shared Discord conversations are
  not shown (open question 1).
- New POST routes, if any appear, are registered in both slash forms (the dev
  proxy strips the trailing slash).
- No new background work.

## Exclusions

- Voice, image input, and file upload in the panel (the files tool has its own
  routes; wiring them into the composer is a later, separate step).
- A full-page chat route. The panel is the only chat surface in this plan.
- Any model picker (S-1).
- Actions that change anything. Mylo can point at a button; it cannot press
  one.
- The Mylo-face button on the public site, in emails, or in the `/labs`
  preview pages.
