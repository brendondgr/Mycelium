"use client";

import * as React from "react";

import { DiscordLink } from "@/components/portal/primitives/discord-link";
import { Card } from "@/components/portal/primitives/card";
import {
  useAnnouncements,
  useCreateAnnouncementChannels,
  useLabProfile,
  useSaveAnnouncementSettings,
  useSendAnnouncementTest,
  useUpdateLabProfile,
} from "@/lib/portal/hooks";
import type {
  AnnouncementServer,
  AnnouncementSettings,
  AnnouncementTarget,
} from "@/lib/portal/types";

const NUDGES: { value: AnnouncementSettings["default_nudge"]; label: string }[] = [
  { value: "2w", label: "2 weeks before (default)" },
  { value: "2d", label: "2 days before" },
  { value: "1w", label: "1 week before" },
  { value: "3w", label: "3 weeks before" },
  { value: "1m", label: "1 month before" },
  { value: "2m", label: "2 months before" },
  { value: "none", label: "No reminder" },
];
const KINDS = [
  ["grants", "Grants"],
  ["fellowships", "Fellowships"],
  ["conferences", "Conferences"],
] as const;
const INSTITUTIONS = [
  ["", "Not said"],
  ["higher_ed", "University or college"],
  ["nonprofit", "Non-profit research institute"],
  ["government", "Government lab or agency"],
  ["company", "Company"],
] as const;

const FIELD =
  "min-h-[44px] w-full rounded-[10px] border border-border bg-surface px-3 text-[14px] text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const BUTTON =
  "inline-flex min-h-[44px] items-center gap-[7px] rounded-full border border-border bg-surface px-4 text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const PRIMARY =
  "inline-flex min-h-[44px] items-center gap-[7px] rounded-full bg-primary px-4 text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

/**
 * Lab (or department) settings → Announcements: the settings for the target, plus
 * one block per Discord server it is bound in, each with its own forums and
 * health. Managers only; replaces the Discord card's channel choices for
 * opportunities.
 */
export function AnnouncementsCard({
  target,
  name,
}: {
  target: AnnouncementTarget;
  name: string;
}) {
  const { data, isLoading, isError } = useAnnouncements(target);
  const save = useSaveAnnouncementSettings(target);
  const test = useSendAnnouncementTest(target);
  const [draft, setDraft] = React.useState<Partial<AnnouncementSettings>>({});
  const settings = data ? { ...data.settings, ...draft } : null;
  const dirty = Object.keys(draft).length > 0;
  const set = <K extends keyof AnnouncementSettings>(key: K, value: AnnouncementSettings[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  if (isLoading) {
    return (
      <Card className="p-5">
        <p className="text-sm text-[var(--text-secondary)]">Loading announcement settings…</p>
      </Card>
    );
  }
  if (isError || !data || !settings) {
    return (
      <Card className="p-5">
        <p className="text-sm text-[var(--text-secondary)]">
          Couldn&apos;t load the announcement settings. Try again in a moment.
        </p>
      </Card>
    );
  }
  if (!data.can_manage) return null;

  const onSave = () =>
    save.mutate(draft, { onSuccess: () => setDraft({}) });

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="m-0 font-serif text-[20px] font-semibold text-[var(--text-primary)]">
            Opportunity announcements
          </h3>
          <p className="m-0 mt-1 max-w-[470px] text-[13.5px] text-[var(--text-secondary)]">
            {"lab" in target ? (
              <>
                One Discord thread per new grant, fellowship or conference that fits{" "}
                {name}, in its own forum. Papers stay in the daily report.
              </>
            ) : (
              <>
                One Discord thread per call only {name} can take on as a department,
                naming the labs that could lead. Calls a lab can apply for alone stay
                with the labs.
              </>
            )}
          </p>
        </div>
        <label className="inline-flex min-h-[44px] items-center gap-2.5 text-[14px] font-medium text-[var(--text-primary)]">
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={(e) => set("enabled", e.target.checked)}
            className="h-5 w-5 accent-[var(--primary)]"
          />
          On
        </label>
      </div>
      {!data.feature_on ? (
        <p className="mt-3 rounded-lg bg-surface-alt px-3 py-2 text-[13px] text-[var(--text-secondary)]">
          Announcements aren&apos;t switched on for this Mycelium yet. Your settings are
          kept and take effect when they are.
        </p>
      ) : null}

      <fieldset className="mt-4">
        <legend className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          What to announce
        </legend>
        <div className="flex flex-wrap gap-4">
          {KINDS.map(([key, label]) => (
            <label key={key} className="inline-flex min-h-[44px] items-center gap-2 text-[14px]">
              <input
                type="checkbox"
                checked={settings[key]}
                onChange={(e) => set(key, e.target.checked)}
                className="h-5 w-5 accent-[var(--primary)]"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-[14px] font-medium">
          Default reminder after &ldquo;Interested&rdquo;
          <select
            className={FIELD}
            value={settings.default_nudge}
            onChange={(e) => set("default_nudge", e.target.value as AnnouncementSettings["default_nudge"])}
          >
            {NUDGES.map((n) => (
              <option key={n.value} value={n.value}>
                {n.label}
              </option>
            ))}
          </select>
          <span className="text-[12.5px] font-normal text-[var(--text-secondary)]">
            Tags them in the thread. &ldquo;Remind me&rdquo; lets each person choose
            their own.
          </span>
        </label>
        <label className="flex flex-col gap-1.5 text-[14px] font-medium">
          New posts per day
          <input
            type="number"
            min={-1}
            className={FIELD}
            value={settings.daily_cap < 0 ? "" : settings.daily_cap}
            placeholder="No limit (default)"
            onChange={(e) => set("daily_cap", e.target.value === "" ? -1 : Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-[14px] font-medium">
          Smallest award worth posting
          <input
            type="number"
            min={0}
            className={FIELD}
            value={settings.min_award ?? ""}
            placeholder="No minimum"
            onChange={(e) => set("min_award", e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>
      </div>

      <div className="mt-4 flex flex-col gap-2">
        <Toggle
          checked={settings.closing_soon_list}
          onChange={(v) => set("closing_soon_list", v)}
          title="Closing-soon list every morning"
          detail="Grants and fellowships closing in the next 14 days, one post each, replaced daily."
        />
        {"lab" in target ? (
          <Toggle
            checked={settings.strong_match_tagging}
            onChange={(v) => set("strong_match_tagging", v)}
            title="Tag people when an item fits them closely"
            detail="Off by default. When on, a post names members whose interests match it strongly."
          />
        ) : null}
      </div>

      {"lab" in target ? <WhoApplies slug={target.lab} /> : null}

      <section aria-label="Discord servers" className="mt-5 flex flex-col gap-3">
        <h4 className="m-0 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
          Where Mylo posts
        </h4>
        {data.servers.length === 0 ? (
          <p className="m-0 text-[13px] text-[var(--text-secondary)]">
            {name} isn&apos;t connected to a Discord server yet. Connect one above, then
            choose its forums here or with <code>/setup</code> in Discord.
          </p>
        ) : (
          data.servers.map((server) => <ServerBlock key={server.binding_id} server={server} />)
        )}
      </section>

      <p className="mt-4 rounded-[12px] bg-surface-alt px-3.5 py-3 text-[13.5px] leading-relaxed text-[var(--text-primary)]">
        The first time you switch this on, Mylo posts the{" "}
        <strong>{settings.activation_seed} most relevant open items</strong>, labelled
        <em> Already open</em>, plus the closing-soon list. After that, only what newly
        enters your list.
      </p>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-2.5">
        {save.isError ? (
          <span role="alert" className="mr-auto text-[13px] text-clay">
            {save.error instanceof Error ? save.error.message : "Couldn't save."}
          </span>
        ) : null}
        {save.data?.activating ? (
          <span role="status" className="mr-auto text-[13px] text-[var(--text-secondary)]">
            Mylo is posting the first items now.
          </span>
        ) : null}
        {test.data ? (
          <span role="status" className="mr-auto text-[13px] text-[var(--text-secondary)]">
            {test.data.results.length
              ? test.data.results
                  .map((r) => `${r.ok ? "Sent" : "Failed"} to #${r.channel_name || r.purpose}`)
                  .join(" · ")
              : "No forums to test yet."}
          </span>
        ) : null}
        <button type="button" className={BUTTON} onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? "Sending…" : "Send a test post"}
        </button>
        <button type="button" className={PRIMARY} onClick={onSave} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </Card>
  );
}

function Toggle({
  checked,
  onChange,
  title,
  detail,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  detail: string;
}) {
  return (
    <label className="flex min-h-[44px] items-start gap-3 text-[14px]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--primary)]"
      />
      <span>
        <strong className="font-semibold text-[var(--text-primary)]">{title}</strong>
        <br />
        <span className="text-[13px] text-[var(--text-secondary)]">{detail}</span>
      </span>
    </label>
  );
}

function ServerBlock({ server }: { server: AnnouncementServer }) {
  const create = useCreateAnnouncementChannels();
  const routes = server.announcement_routes;
  const hasRoutes = Object.keys(routes).length > 0;
  return (
    <div className="rounded-[14px] border border-[var(--divider)] bg-surface-alt p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[14px] font-semibold text-[var(--text-primary)]">
          {server.guild_name || "Discord server"}
        </span>
        <span className="text-[12px] text-[var(--text-secondary)]">
          {server.state === "active"
            ? "Connected"
            : server.state === "kicked"
              ? "Mylo was removed"
              : "Setup pending"}
        </span>
      </div>
      {hasRoutes ? (
        <ul className="mt-2 flex flex-col gap-1.5">
          {KINDS.map(([key, label]) => {
            const route = routes[key];
            return (
              <li key={key} className="flex flex-wrap items-center gap-2 text-[13.5px]">
                <span className="w-[100px] shrink-0 font-medium text-[var(--text-primary)]">{label}</span>
                {route ? (
                  <>
                    <DiscordLink
                      what="channel"
                      fallbackChannel={key}
                      links={[
                        {
                          guild_id: server.guild_id,
                          guild_name: server.guild_name,
                          channel_id: route.channel_id,
                          channel_name: route.channel_name,
                          thread_url: `https://discord.com/channels/${server.guild_id}/${route.channel_id}`,
                        },
                      ]}
                    />
                    <span className={route.ok === false ? "text-clay" : "text-[var(--text-secondary)]"}>
                      {route.ok === false
                        ? "Mylo can't post here. Check the forum's permissions"
                        : route.poster_policy === "everyone"
                          ? "Anyone can start posts"
                          : route.poster_policy === "managers"
                            ? "Managers start posts"
                            : "Chosen roles start posts"}
                    </span>
                  </>
                ) : (
                  <span className="text-[var(--text-secondary)]">Not set</span>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={BUTTON}
            onClick={() => create.mutate(server.binding_id)}
            disabled={create.isPending || server.state !== "active"}
          >
            {create.isPending ? "Creating…" : "Create them for me"}
          </button>
          <span className="text-[12.5px] text-[var(--text-secondary)]">
            {server.target_kind === "department"
              ? "Makes a category with one #dept-opportunities forum."
              : "Makes a category with three forums."} Or pick existing forums with{" "}
            <code>/setup</code> in Discord.
          </span>
          {create.data && !create.data.ok ? (
            <span role="alert" className="text-[12.5px] text-clay">{create.data.message}</span>
          ) : null}
          {create.isError ? (
            <span role="alert" className="text-[12.5px] text-clay">
              {create.error instanceof Error ? create.error.message : "Couldn't create the forums."}
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** The lab profile's institution type and country: what the eligibility checks read. */
function WhoApplies({ slug }: { slug: string }) {
  const profile = useLabProfile(slug);
  const update = useUpdateLabProfile(slug);
  const [type, setType] = React.useState<string | null>(null);
  const [country, setCountry] = React.useState<string | null>(null);
  const current = profile.data;
  if (!current) return null;
  const typeValue = type ?? current.institution_type ?? "";
  const countryValue = country ?? current.country ?? "";
  const changed = type !== null || country !== null;
  return (
    <fieldset className="mt-4 rounded-[14px] border border-[var(--divider)] p-3.5">
      <legend className="px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Who applies
      </legend>
      <p className="m-0 mb-2 text-[12.5px] text-[var(--text-secondary)]">
        Checked against each call&apos;s applicant types and countries. Left blank, those
        checks say &ldquo;unknown&rdquo;.
      </p>
      <div className="grid gap-3 sm:grid-cols-[1fr_140px_auto] sm:items-end">
        <label className="flex flex-col gap-1.5 text-[14px] font-medium">
          Institution
          <select className={FIELD} value={typeValue} onChange={(e) => setType(e.target.value)}>
            {INSTITUTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-[14px] font-medium">
          Country
          <input
            className={FIELD}
            value={countryValue}
            maxLength={2}
            placeholder="e.g. US"
            onChange={(e) => setCountry(e.target.value.toUpperCase())}
            aria-describedby="country-help"
          />
        </label>
        <button
          type="button"
          className={BUTTON}
          disabled={!changed || update.isPending}
          onClick={() =>
            update.mutate(
              {
                institution_type: typeValue as "" | "higher_ed" | "nonprofit" | "government" | "company",
                country: countryValue,
              },
              { onSuccess: () => { setType(null); setCountry(null); } },
            )
          }
        >
          {update.isPending ? "Saving…" : "Save"}
        </button>
      </div>
      <span id="country-help" className="sr-only">Two-letter country code</span>
      {update.isError ? (
        <p role="alert" className="m-0 mt-2 text-[12.5px] text-clay">
          {update.error instanceof Error ? update.error.message : "Couldn't save."}
        </p>
      ) : null}
    </fieldset>
  );
}
