"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Modal, ModalHeader } from "@/components/portal/primitives/modal";
import {
  assembleTeam,
  fetchIntroduction,
  prefillSearch,
  runSearch,
  sendMatchFeedback,
} from "@/lib/portal/collab/client";
import {
  useSavedPeople,
  useSearchAvailability,
} from "@/lib/portal/collab/hooks";
import type {
  Audience,
  Lane,
  QuerySlot,
  SearchEntry,
  SearchHit,
  Introduction,
  SearchResponse,
  SlotFacet,
  TeamResponse,
} from "@/lib/portal/collab/types";

const LANES: { value: Lane; label: string; note: string }[] = [
  {
    value: "method_bridge",
    label: "Method from another field",
    note: "brings a technique you lack",
  },
  {
    value: "problem_bridge",
    label: "Same problem, another approach",
    note: "attacks it differently",
  },
  {
    value: "resource",
    label: "Holds the data",
    note: "a dataset, cohort, or instrument",
  },
  { value: "in_field", label: "In your field", note: "could share the work" },
];
const LANE_LABEL = Object.fromEntries(
  LANES.map((l) => [l.value, l.label]),
) as Record<Lane, string>;

const FACETS: { value: SlotFacet; label: string }[] = [
  { value: "problem", label: "Problem" },
  { value: "method", label: "Method" },
  { value: "data", label: "Data" },
  { value: "role", label: "Partner" },
];

const SCOPES: { value: Audience; label: string }[] = [
  { value: "institution", label: "My institution" },
  { value: "country", label: "My country" },
  { value: "anywhere", label: "Anywhere" },
];

/** Open the collaborator search from anywhere: a card, a project, the palette. */
export type CollabSearchRequest = {
  entry: SearchEntry;
  title: string;
  slots?: QuerySlot[];
};

export const COLLAB_SEARCH_EVENT = "mycelium:collab-search";

export function openCollaboratorSearch(request: CollabSearchRequest) {
  window.dispatchEvent(
    new CustomEvent(COLLAB_SEARCH_EVENT, { detail: request }),
  );
}

/** A refusal reason from the API ("verify your email to search") as a sentence. */
export function sentence(text: string): string {
  if (!text) return text;
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

/**
 * Mounted once in the workspace shell; opens the panel when any entry point
 * asks. Decoupled by an event so a feed card, a project tab and the command
 * palette need no shared state to reach the same panel.
 */
export function CollaboratorSearchHost() {
  const [request, setRequest] = React.useState<CollabSearchRequest | null>(
    null,
  );
  React.useEffect(() => {
    const open = (event: Event) =>
      setRequest((event as CustomEvent<CollabSearchRequest>).detail);
    window.addEventListener(COLLAB_SEARCH_EVENT, open);
    return () => window.removeEventListener(COLLAB_SEARCH_EVENT, open);
  }, []);
  if (!request) return null;
  return (
    <SearchPanel
      key={JSON.stringify(request.entry)}
      request={request}
      onClose={() => setRequest(null)}
    />
  );
}

/**
 * The collaborator search (collaboration-network plan CN-06): a side panel, so
 * the call or project it came from stays in view.
 *
 * The need arrives pre-filled — a call's requirements, a project's stated
 * state, or the reader's own words — as editable slots. Nothing searches until
 * Run. Results come back in two groups that are never merged into one ranking:
 * people who **fill a gap** (a method from another field, the same problem by
 * another approach, the data) and people who **share the expertise** you have.
 * Each is a pointer, not a profile: name, institution, the one thing that
 * matched and where that comes from, and Mylo's line on why.
 */
export function SearchPanel({
  request,
  onClose,
}: {
  request: CollabSearchRequest;
  onClose: () => void;
}) {
  const availability = useSearchAvailability();
  const manual = request.entry.entry === "manual";
  const prefill = useQuery({
    queryKey: ["collab", "prefill", request.entry],
    queryFn: () => prefillSearch(request.entry),
    enabled: !request.slots && !manual && availability.data?.available === true,
  });
  const [slots, setSlots] = React.useState<QuerySlot[] | null>(
    request.slots ?? null,
  );
  const shownSlots = slots ?? prefill.data?.slots ?? [];
  const [lanes, setLanes] = React.useState<Lane[]>(LANES.map((l) => l.value));
  const [scope, setScope] = React.useState<Audience>("institution");
  const [text, setText] = React.useState(
    request.entry.entry === "manual" ? request.entry.text : "",
  );
  const [outsideNetwork, setOutsideNetwork] = React.useState(false);
  const entry: SearchEntry = manual ? { entry: "manual", text } : request.entry;
  const sentSlots = shownSlots.map(({ facet, text: slotText, required }) => ({
    facet,
    text: slotText,
    required,
  }));
  const search = useMutation({
    // The scope is the mutation's variable so the empty state names the place
    // that was searched, not whatever the selector says now.
    mutationFn: (searched: Audience) =>
      runSearch(entry, {
        slots: sentSlots,
        lanes,
        scope: searched,
        outside_network: outsideNetwork,
      }),
  });
  const team = useMutation({
    mutationFn: () =>
      assembleTeam(entry, {
        slots: sentSlots,
        scope,
        outside_network: outsideNetwork,
      }),
  });
  // A team is offered for three or more needs the reader does not already
  // cover; the server decides for certain (it re-reads coverage).
  const openNeeds = shownSlots.filter(
    (s) => s.facet !== "role" && s.covered_by !== "you",
  ).length;
  const readWords = useMutation({
    mutationFn: () => prefillSearch({ entry: "manual", text }),
    onSuccess: (data) => setSlots(data.slots),
  });

  const maxScope = availability.data?.max_scope ?? "institution";
  const allowedScopes = SCOPES.slice(
    0,
    SCOPES.findIndex((s) => s.value === maxScope) + 1,
  );

  return (
    <Modal onClose={onClose} label="Find collaborators" width="side">
      <ModalHeader
        eyebrow="Find collaborators"
        title={request.title}
        onClose={onClose}
      />
      <div className="flex-1 space-y-5 px-5 py-4">
        {availability.data && !availability.data.available ? (
          <p className="text-sm text-[var(--text-secondary)]">
            {sentence(availability.data.reason)}
          </p>
        ) : null}

        {manual ? (
          <div>
            <label
              htmlFor="collab-need"
              className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]"
            >
              What do you need?
            </label>
            <textarea
              id="collab-need"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. We need someone who can quantify uncertainty in satellite estimates of reef temperature."
              className="mt-1.5 w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <button
              type="button"
              disabled={!text.trim() || readWords.isPending}
              onClick={() => readWords.mutate()}
              className="mt-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-50"
            >
              {readWords.isPending ? "Reading…" : "Turn into requirements"}
            </button>
            {readWords.isError ? (
              <p role="alert" className="mt-1.5 text-sm text-clay">
                {(readWords.error as Error).message}
              </p>
            ) : null}
          </div>
        ) : null}

        <SlotEditor
          slots={shownSlots}
          onChange={setSlots}
          loading={prefill.isLoading}
        />

        <fieldset>
          <legend className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
            Look for
          </legend>
          <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
            {LANES.map((lane) => (
              <label
                key={lane.value}
                className="flex items-start gap-2 text-sm text-[var(--text-secondary)]"
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={lanes.includes(lane.value)}
                  onChange={(event) =>
                    setLanes((current) =>
                      event.target.checked
                        ? [...current, lane.value]
                        : current.filter((v) => v !== lane.value),
                    )
                  }
                />
                <span>
                  <span className="text-[var(--text-primary)]">
                    {lane.label}
                  </span>
                  <span className="block text-[12px] text-[var(--text-muted)]">
                    {lane.note}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            className="mt-1"
            checked={outsideNetwork}
            onChange={(event) => setOutsideNetwork(event.target.checked)}
          />
          <span>
            Outside my network
            <span className="block text-[12px] text-[var(--text-muted)]">
              also leave out people your co-authors have published with
            </span>
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor="collab-scope"
            className="text-sm text-[var(--text-secondary)]"
          >
            Where
          </label>
          <select
            id="collab-scope"
            value={scope}
            onChange={(event) => setScope(event.target.value as Audience)}
            className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-[var(--text-primary)]"
          >
            {allowedScopes.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={
              search.isPending ||
              !availability.data?.available ||
              lanes.length === 0 ||
              shownSlots.filter((s) => s.facet !== "role").length === 0
            }
            onClick={() => search.mutate(scope)}
            className="ml-auto rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-[#fffdf8] disabled:opacity-60"
          >
            {search.isPending ? "Searching…" : "Run"}
          </button>
        </div>
        {openNeeds >= 3 && availability.data?.available ? (
          <button
            type="button"
            disabled={team.isPending}
            onClick={() => team.mutate()}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
          >
            {team.isPending ? "Assembling…" : "Assemble a team"}
          </button>
        ) : null}
        {team.isError ? (
          <p role="alert" className="text-sm text-clay">
            {(team.error as Error).message}
          </p>
        ) : null}
        {team.data ? <TeamResult result={team.data} /> : null}
        {search.isError ? (
          <p role="alert" className="text-sm text-clay">
            {(search.error as Error).message}
          </p>
        ) : null}

        {search.data ? (
          <Results result={search.data} scope={search.variables ?? scope} />
        ) : null}

        <SavedPeople />
      </div>
    </Modal>
  );
}

function SlotEditor({
  slots,
  onChange,
  loading,
}: {
  slots: QuerySlot[];
  onChange: (next: QuerySlot[]) => void;
  loading: boolean;
}) {
  const [facet, setFacet] = React.useState<SlotFacet>("method");
  const [draft, setDraft] = React.useState("");
  return (
    <div>
      <p className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
        The need
      </p>
      {loading ? (
        <p className="mt-1.5 text-sm text-[var(--text-muted)]">
          Reading the requirements…
        </p>
      ) : slots.length === 0 ? (
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          Nothing to search for yet — add what the work needs below.
        </p>
      ) : (
        <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Requirements">
          {slots.map((slot, index) => (
            <li
              key={`${slot.facet}:${slot.text}`}
              className="flex items-center gap-1 rounded-full border border-border bg-surface-alt px-2.5 py-1 text-[12.5px] text-[var(--text-primary)]"
            >
              <span className="text-[10.5px] font-semibold uppercase text-[var(--text-muted)]">
                {FACETS.find((f) => f.value === slot.facet)?.label}
              </span>
              <span>{slot.text}</span>
              {slot.facet !== "role" && slot.covered_by !== undefined ? (
                <span
                  className={
                    slot.covered_by === null
                      ? "text-[11px] font-medium text-clay"
                      : "text-[11px] text-[var(--text-muted)]"
                  }
                >
                  {slot.covered_by === "you"
                    ? "you cover"
                    : slot.covered_by === "lab"
                      ? "lab covers"
                      : "gap"}
                </span>
              ) : null}
              <button
                type="button"
                aria-label={`Remove ${slot.text}`}
                onClick={() => onChange(slots.filter((_, i) => i !== index))}
                className="ml-0.5 flex h-5 w-5 items-center justify-center rounded-full text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="mt-2 flex flex-wrap gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          const value = draft.trim();
          if (value) {
            onChange([...slots, { facet, text: value }]);
            setDraft("");
          }
        }}
      >
        <select
          aria-label="Kind of requirement"
          value={facet}
          onChange={(event) => setFacet(event.target.value as SlotFacet)}
          className="rounded-lg border border-border bg-surface px-2 py-1 text-sm"
        >
          {FACETS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={90}
          placeholder="Add a requirement"
          aria-label="Add a requirement"
          className="min-w-[10rem] flex-1 rounded-lg border border-border bg-surface px-2.5 py-1 text-sm placeholder:text-[var(--text-muted)]"
        />
        <button
          type="submit"
          disabled={!draft.trim()}
          className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium disabled:opacity-50"
        >
          Add
        </button>
      </form>
    </div>
  );
}

const PLACE: Record<Audience, string> = {
  institution: "at your institution",
  country: "in your country",
  anywhere: "anywhere",
};

function Results({
  result,
  scope,
}: {
  result: SearchResponse;
  scope: Audience;
}) {
  const empty =
    result.groups.fills_a_gap.length === 0 &&
    result.groups.shares_expertise.length === 0;
  if (empty) {
    // Never a padded list, and never a count of who was filtered out — that
    // count would say who is open to collaboration and who is not.
    return (
      <p className="rounded-lg border border-border px-3 py-2.5 text-sm text-[var(--text-secondary)]">
        Nobody {PLACE[scope]} who is open to collaboration matches this yet.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {!result.explained ? (
        <p className="text-[12.5px] text-[var(--text-muted)]">
          Mylo&apos;s explanations are unavailable right now; results are in
          match order.
        </p>
      ) : null}
      <Group
        title="Fills a gap"
        hits={result.groups.fills_a_gap}
        searchId={result.search_id}
      />
      <Group
        title="Shares your expertise"
        hits={result.groups.shares_expertise}
        searchId={result.search_id}
      />
    </div>
  );
}

function Group({
  title,
  hits,
  searchId,
}: {
  title: string;
  hits: SearchHit[];
  searchId: number;
}) {
  if (hits.length === 0) return null;
  return (
    <section>
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
        {title}
      </h3>
      <ul className="mt-2 space-y-2">
        {hits.map((hit) => (
          <HitCard
            key={`${hit.lane}:${hit.username}:${hit.slot}`}
            hit={hit}
            searchId={searchId}
          />
        ))}
      </ul>
    </section>
  );
}

function HitCard({ hit, searchId }: { hit: SearchHit; searchId: number }) {
  const [sent, setSent] = React.useState<"save" | "not_relevant" | null>(null);
  const send = (kind: "save" | "not_relevant") =>
    sendMatchFeedback(searchId, {
      candidate: hit.username,
      lane: hit.lane,
      kind,
    })
      .then(() => setSent(kind))
      .catch(() => setSent(null));
  return (
    <li className="rounded-xl border border-border px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium text-[var(--text-primary)]">
          {hit.name}
        </span>
        {hit.institution ? (
          <span className="text-[12.5px] text-[var(--text-secondary)]">
            {hit.institution}
          </span>
        ) : null}
        <span className="ml-auto rounded-full border border-border px-2 py-px text-[11px] text-[var(--text-muted)]">
          {LANE_LABEL[hit.lane]}
        </span>
      </div>
      <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
        {hit.matched}{" "}
        <span className="text-[11.5px] text-[var(--text-muted)]">
          (
          {hit.tier === "demonstrated"
            ? "from their papers"
            : "from their profile"}{" "}
          · for “{hit.slot}”)
        </span>
      </p>
      {hit.reason ? (
        <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-primary)]">
          {hit.reason}
        </p>
      ) : null}
      <IntroductionLine searchId={searchId} username={hit.username} />
      <div className="mt-2 flex gap-1.5">
        {sent ? (
          <span className="text-[12px] text-[var(--text-muted)]">
            {sent === "save" ? "Saved" : "Noted — thank you"}
          </span>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void send("save")}
              className="rounded-md border border-border px-2 py-0.5 text-[12px] hover:bg-surface-alt"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => void send("not_relevant")}
              className="rounded-md border border-border px-2 py-0.5 text-[12px] text-[var(--text-secondary)] hover:bg-surface-alt"
            >
              Not relevant
            </button>
          </>
        )}
      </div>
    </li>
  );
}

/**
 * "Who can introduce me?" (plan CN-07) — asked on demand, one person at a
 * time. Only people who are themselves open to the reader are ever named.
 */
function IntroductionLine({
  searchId,
  username,
}: {
  searchId: number;
  username: string;
}) {
  const [asked, setAsked] = React.useState(false);
  const via = useQuery<Introduction>({
    queryKey: ["collab", "introduction", searchId, username],
    queryFn: () => fetchIntroduction(searchId, username),
    enabled: asked,
    staleTime: Infinity,
  });
  if (!asked) {
    return (
      <button
        type="button"
        onClick={() => setAsked(true)}
        className="mt-1 text-[12px] font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
      >
        Who can introduce me?
      </button>
    );
  }
  if (via.isLoading) {
    return <p className="mt-1 text-[12px] text-[var(--text-muted)]">Looking…</p>;
  }
  if (via.isError || !via.data?.path) {
    return (
      <p className="mt-1 text-[12px] text-[var(--text-muted)]">
        No introduction through people open to you.
      </p>
    );
  }
  return (
    <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
      Via{" "}
      {via.data.path
        .map((p) => (p.institution ? `${p.name} (${p.institution})` : p.name))
        .join(" → ")}
    </p>
  );
}

function TeamResult({ result }: { result: TeamResponse }) {
  if (result.team.length === 0) {
    return (
      <p className="rounded-lg border border-border px-3 py-2.5 text-sm text-[var(--text-secondary)]">
        Nobody open to collaboration covers these gaps yet.
      </p>
    );
  }
  return (
    <section>
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
        A proposed team
      </h3>
      <ul className="mt-2 space-y-2">
        {result.team.map((member) => (
          <li
            key={member.username}
            className="rounded-xl border border-border px-3 py-2.5"
          >
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium text-[var(--text-primary)]">
                {member.name}
              </span>
              {member.institution ? (
                <span className="text-[12.5px] text-[var(--text-secondary)]">
                  {member.institution}
                </span>
              ) : null}
              {member.distance !== null ? (
                <span className="ml-auto text-[11px] text-[var(--text-muted)]">
                  {member.distance} co-authorship
                  {member.distance === 1 ? "" : "s"} from you
                </span>
              ) : null}
            </div>
            <ul className="mt-1 space-y-0.5 text-[13px] text-[var(--text-secondary)]">
              {member.covers.map((c) => (
                <li key={c.slot}>
                  {c.matched}{" "}
                  <span className="text-[11.5px] text-[var(--text-muted)]">
                    (
                    {c.tier === "demonstrated"
                      ? "from their papers"
                      : "from their profile"}{" "}
                    · for “{c.slot}”)
                  </span>
                </li>
              ))}
            </ul>
            <IntroductionLine
              searchId={result.search_id}
              username={member.username}
            />
          </li>
        ))}
      </ul>
      {result.uncovered.length > 0 ? (
        <p className="mt-2 text-[12.5px] text-[var(--text-muted)]">
          Nobody open to you covers: {result.uncovered.join(", ")}.
        </p>
      ) : null}
    </section>
  );
}

function SavedPeople() {
  const [open, setOpen] = React.useState(false);
  const saved = useSavedPeople(open);
  return (
    <div className="border-t border-[var(--divider)] pt-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
      >
        {open ? "Hide saved people" : "Saved people"}
      </button>
      {open ? (
        saved.data && saved.data.people.length > 0 ? (
          <ul className="mt-2 space-y-1 text-sm">
            {saved.data.people.map((person) => (
              <li
                key={person.username}
                className="text-[var(--text-secondary)]"
              >
                <span className="text-[var(--text-primary)]">
                  {person.name}
                </span>{" "}
                · {LANE_LABEL[person.lane]}
                {person.slots.length
                  ? ` · for ${person.slots.slice(0, 2).join(", ")}`
                  : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-[var(--text-muted)]">
            {saved.isLoading ? "Loading…" : "Nobody saved yet."}
          </p>
        )
      ) : null}
    </div>
  );
}
