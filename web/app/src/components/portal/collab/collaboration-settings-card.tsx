"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import {
  useCollaborationPreview,
  useCollaborationSetting,
  useSaveCollaborationSetting,
} from "@/lib/portal/collab/hooks";
import type {
  Audience,
  CollaborationSetting,
  OpenTo,
} from "@/lib/portal/collab/types";

const AUDIENCES: { value: Audience; label: string }[] = [
  { value: "institution", label: "My institution" },
  { value: "country", label: "My country" },
  { value: "anywhere", label: "Anywhere" },
];

const OPEN_TO: { value: OpenTo; label: string }[] = [
  { value: "co_authoring", label: "Co-authoring" },
  { value: "grant_partner", label: "Grant partner" },
  { value: "data_sharing", label: "Sharing data" },
  { value: "mentoring", label: "Mentoring" },
];

const FACET_LABEL: Record<string, string> = {
  problem: "Problems",
  method: "Methods",
  setting: "Data and settings",
  area: "Research areas",
};

/**
 * "Open to collaboration" — whether other researchers searching for a
 * collaborator can find you, and who (collaboration-network plan CN-04).
 *
 * Off by default and off again after six months unless renewed. Where you can
 * be found is decided by your **verified** email's institution, never by the
 * affiliation you type. The preview is exactly what a seeker would see — and
 * what Mylo learned from conversation is never in it, because it can never be
 * matched. Nobody is told you were found, and you are not told who looked.
 */
export function CollaborationSettingsCard() {
  const setting = useCollaborationSetting();
  // Keyed on arrival, so the form mounts once with real initial values rather
  // than syncing them in through an effect (the Account page's own pattern).
  return (
    <CollaborationForm
      key={setting.data ? "loaded" : "loading"}
      data={setting.data}
      failed={setting.isError}
    />
  );
}

function CollaborationForm({
  data,
  failed,
}: {
  data: CollaborationSetting | undefined;
  failed: boolean;
}) {
  const save = useSaveCollaborationSetting();
  const [showPreview, setShowPreview] = React.useState(false);
  const preview = useCollaborationPreview(showPreview);
  const [audience, setAudience] = React.useState<Audience>(() =>
    data && data.allowed_audiences.includes(data.audience)
      ? data.audience
      : (data?.allowed_audiences[0] ?? "institution"),
  );
  const [openTo, setOpenTo] = React.useState<OpenTo[]>(data?.open_to ?? []);
  const [error, setError] = React.useState<string | null>(null);

  const submit = (open: boolean, renew = false) => {
    setError(null);
    save.mutate(
      { open, audience, open_to: openTo, renew },
      { onError: (err) => setError((err as Error).message) },
    );
  };

  return (
    <Card className="mb-9 p-[22px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg text-[var(--text-primary)]">
            Collaboration
          </h2>
          <p className="mt-1 max-w-[62ch] text-sm leading-relaxed text-[var(--text-secondary)]">
            Let researchers who are looking for a collaborator find you. Off
            unless you turn it on, and it switches itself off after six months.
            You can search for collaborators yourself whether this is on or
            off.
          </p>
        </div>
        {data ? (
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
              data.open
                ? "border-primary text-primary"
                : "border-border text-[var(--text-muted)]"
            }`}
          >
            {data.open ? "Open" : "Off"}
          </span>
        ) : null}
      </div>

      {failed ? (
        <p className="mt-3 text-sm text-clay">Couldn&apos;t load this. Refresh to try again.</p>
      ) : null}

      {data && !data.verified ? (
        <p className="mt-3 text-sm text-[var(--text-secondary)]">
          Verify your email first: where you can be found is worked out from the
          institution your verified email belongs to.
        </p>
      ) : null}

      {data && data.verified ? (
        <div className="mt-4 space-y-4">
          <p className="text-sm text-[var(--text-secondary)]">
            {data.institution
              ? `Your verified email places you at ${data.institution}.`
              : "Your verified email isn't at an institution Mylo recognises, so you can't be found or search for people. People are suggested only from the institution or country an email proves — change your email on this page to your institution's address."}
          </p>

          <fieldset>
            <legend className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
              Who can find me
            </legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {AUDIENCES.map((option) => {
                const allowed = data.allowed_audiences.includes(option.value);
                const on = audience === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    disabled={!allowed}
                    aria-pressed={on}
                    onClick={() => setAudience(option.value)}
                    className={`rounded-full border px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      on
                        ? "border-primary bg-primary text-[#fffdf8]"
                        : "border-border text-[var(--text-secondary)] hover:bg-surface-alt"
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">
              Open to
            </legend>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
              {OPEN_TO.map((option) => (
                <label
                  key={option.value}
                  className="flex items-center gap-2 text-sm text-[var(--text-secondary)]"
                >
                  <input
                    type="checkbox"
                    checked={openTo.includes(option.value)}
                    onChange={(event) =>
                      setOpenTo((current) =>
                        event.target.checked
                          ? [...current, option.value]
                          : current.filter((value) => value !== option.value),
                      )
                    }
                  />
                  {option.label}
                </label>
              ))}
            </div>
            <p className="mt-2 max-w-[62ch] text-[13px] leading-relaxed text-[var(--text-muted)]">
              These help people looking for that kind of collaboration find
              you. They never hide you from anyone else in your audience.
            </p>
          </fieldset>

          <p className="rounded-lg border border-border bg-surface-alt/60 px-3 py-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Choosing who can find you limits where you appear. It does not
            guarantee who sees you. Anyone in your audience who searches for
            what you work on may see your name, your institution, and the topic
            that matched. People are never told someone searched for them, and
            neither are you.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {data.open ? (
              <>
                <button
                  type="button"
                  onClick={() => submit(true)}
                  disabled={save.isPending}
                  className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-[#fffdf8] disabled:opacity-60"
                >
                  Save changes
                </button>
                <button
                  type="button"
                  onClick={() => submit(true, true)}
                  disabled={save.isPending}
                  className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
                >
                  Renew for six months
                </button>
                <button
                  type="button"
                  onClick={() => submit(false)}
                  disabled={save.isPending}
                  className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-clay hover:bg-surface-alt disabled:opacity-60"
                >
                  Turn off
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => submit(true)}
                disabled={save.isPending || data.allowed_audiences.length === 0}
                className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-[#fffdf8] disabled:opacity-60"
              >
                Turn on
              </button>
            )}
            {data.open && data.expires_at ? (
              <span className="text-xs text-[var(--text-muted)]">
                On until {new Date(data.expires_at).toLocaleDateString()}
              </span>
            ) : null}
          </div>
          {error ? (
            <p role="alert" className="text-sm text-clay">
              {error}
            </p>
          ) : null}

          <div>
            <button
              type="button"
              onClick={() => setShowPreview((value) => !value)}
              aria-expanded={showPreview}
              className="text-sm font-medium text-[var(--text-secondary)] underline-offset-2 hover:underline"
            >
              {showPreview ? "Hide what others would see" : "See what others would see"}
            </button>
            {showPreview ? (
              <div className="mt-2 rounded-lg border border-border px-3 py-2.5 text-sm">
                {preview.isLoading ? (
                  <p className="text-[var(--text-muted)]">Loading…</p>
                ) : preview.data ? (
                  <>
                    <p className="font-medium text-[var(--text-primary)]">
                      {preview.data.name}
                      {preview.data.institution ? ` · ${preview.data.institution}` : ""}
                    </p>
                    {Object.keys(preview.data.facets).length === 0 ? (
                      <p className="mt-1 text-[var(--text-secondary)]">
                        Nothing a search could match yet — add research areas or
                        import your papers.
                      </p>
                    ) : (
                      <dl className="mt-2 space-y-1.5">
                        {Object.entries(preview.data.facets).map(([facet, items]) => (
                          <div key={facet}>
                            <dt className="text-[11.5px] font-semibold uppercase tracking-[0.04em] text-[var(--text-muted)]">
                              {FACET_LABEL[facet] ?? facet}
                            </dt>
                            <dd className="text-[var(--text-secondary)]">
                              {(items ?? [])
                                .map((item) => `${item.label} (${item.sources.join(", ")})`)
                                .join(" · ")}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    <p className="mt-2 text-[12px] text-[var(--text-muted)]">
                      What Mylo understood from conversation is never shown here,
                      and can never make you findable.
                    </p>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </Card>
  );
}
