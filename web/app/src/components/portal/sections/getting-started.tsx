"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Circle, CircleCheck, CircleDashed, Copy, RefreshCw } from "lucide-react";

import { useAppHref } from "@/components/demo/demo-context";
import { LinesSkeleton } from "@/components/portal/skeleton";
import { ApiError } from "@/lib/api-error";
import { buildApiUrl, getPublicApiBase } from "@/lib/api-url";
import { SECTION_ROUTES } from "@/lib/portal/routes";

/**
 * "Getting started": what a new instance still needs, for its administrators.
 *
 * Each step turns done from a real check on the server
 * (`GET /api/admin/setup-status/`, staff-only): the model answers or is off on
 * purpose, the corpus holds items, the admin's profile has interests, someone
 * else has an account or an invitation, and (optionally) Mylo is in a Discord
 * server. While the first collection is still to come the list re-checks every
 * half minute, so the counts fill in as it runs. Once the four required steps
 * are done the card is gone.
 */

type StepState = "done" | "todo" | "skipped" | "optional";

type SetupStatus = {
  complete: boolean;
  steps: {
    model: { state: StepState; detail?: string };
    collection: {
      state: StepState;
      counts: Record<"paper" | "grant" | "conference" | "fellowship", number>;
      total: number;
      last_run: { finished_at: string | null; ok: boolean } | null;
      command: string;
    };
    profile: { state: StepState };
    people: { state: StepState; users: number; invites: number };
    discord: { state: StepState; servers: number; bot_configured: boolean };
  };
};

async function fetchSetupStatus(): Promise<SetupStatus> {
  const response = await fetch(buildApiUrl(getPublicApiBase(), "admin", "setup-status"), {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError("Could not load the setup checklist.", response.status);
  }
  return (await response.json()) as SetupStatus;
}

export function useSetupStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["portal", "admin-setup-status"],
    queryFn: fetchSetupStatus,
    enabled,
    staleTime: 15_000,
    // Re-check while the first collection is still to come, so its counts
    // appear as it runs; stop once there is a corpus.
    refetchInterval: (query) =>
      query.state.data && query.state.data.steps.collection.state !== "done" ? 30_000 : false,
  });
}

const NUMBER = new Intl.NumberFormat();

function plural(n: number, one: string, many: string): string {
  return `${NUMBER.format(n)} ${n === 1 ? one : many}`;
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = React.useState(false);
  const copy = React.useCallback(() => {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(command).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      },
      () => undefined,
    );
  }, [command]);
  return (
    <span className="mt-1.5 inline-flex max-w-full items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface-alt,transparent)] py-0.5 pl-2 pr-0.5">
      <code className="min-w-0 overflow-x-auto whitespace-nowrap font-mono text-[12.5px] text-[var(--text-primary)]">
        {command}
      </code>
      <button
        type="button"
        onClick={copy}
        className="inline-flex size-7 shrink-0 items-center justify-center rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--primary)]"
        aria-label={copied ? "Copied" : `Copy the command ${command}`}
        title={copied ? "Copied" : "Copy"}
      >
        {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      </button>
    </span>
  );
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done" || state === "skipped") {
    return <CircleCheck size={20} className="text-[var(--primary)]" aria-hidden="true" />;
  }
  if (state === "optional") {
    return <CircleDashed size={20} className="text-[var(--text-muted)]" aria-hidden="true" />;
  }
  return <Circle size={20} className="text-[var(--text-muted)]" aria-hidden="true" />;
}

function stateLabel(state: StepState): string {
  return { done: "Done", skipped: "Done", todo: "To do", optional: "Optional" }[state];
}

type Step = {
  key: string;
  state: StepState;
  title: string;
  body: React.ReactNode;
};

function useSteps(status: SetupStatus): Step[] {
  const appHref = useAppHref();
  const { model, collection, profile, people, discord } = status.steps;
  const counts = collection.counts;
  const countLine = [
    plural(counts.paper, "paper", "papers"),
    plural(counts.grant, "grant", "grants"),
    plural(counts.conference, "conference", "conferences"),
    plural(counts.fellowship, "fellowship", "fellowships"),
  ].join(" · ");

  return [
    {
      key: "model",
      state: model.state,
      title:
        model.state === "done"
          ? "Language model connected"
          : model.state === "skipped"
            ? "Running without a language model"
            : "Connect a language model, or continue without one",
      body:
        model.state === "done" ? (
          <p>{model.detail}</p>
        ) : model.state === "skipped" ? (
          <p>
            Write-ups and profile drafts use plain templates. To connect one later, set LLM_BASE_URL and
            LLM_MODEL in .env, turn llm.enabled back on and restart.
          </p>
        ) : (
          <>
            <p>
              {model.detail ? `${model.detail}. ` : ""}Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in the
              server&rsquo;s .env and run <code className="font-mono">make restart</code>, or carry on
              without one:
            </p>
            <CommandLine command="ops/mycelium config set llm.enabled false" />
          </>
        ),
    },
    {
      key: "collection",
      state: collection.state,
      title: collection.state === "done" ? "First collection in" : "Run the first collection",
      body:
        collection.state === "done" ? (
          <p>{countLine}. Each night the run collects again and re-ranks everything.</p>
        ) : (
          <>
            <p>
              Papers, grants, conferences and fellowships are collected once a day. Run the first collection
              now, on the server:
            </p>
            <CommandLine command={collection.command} />
            {collection.last_run && !collection.last_run.ok ? (
              <p className="mt-1.5 text-[var(--warn,var(--text-secondary))]">
                The last run stopped before it finished. <code className="font-mono">make logs</code> and{" "}
                <code className="font-mono">make doctor</code> show why.
              </p>
            ) : null}
            <p className="mt-1.5 text-[var(--text-muted)]" aria-live="polite">
              {collection.total > 0 ? `So far: ${countLine}.` : "This list updates as items arrive."}
            </p>
          </>
        ),
    },
    {
      key: "profile",
      state: profile.state,
      title: profile.state === "done" ? "Your profile is filled in" : "Fill in your research profile",
      body:
        profile.state === "done" ? (
          <p>Mylo ranks what it collects against it.</p>
        ) : (
          <p>
            Mylo ranks everything it collects against your research interests.{" "}
            <Link className="ws-link" href={appHref(SECTION_ROUTES.profile)}>
              Open your profile <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </p>
        ),
    },
    {
      key: "people",
      state: people.state,
      title: people.state === "done" ? "People are joining" : "Invite people",
      body:
        people.state === "done" ? (
          <p>
            {plural(people.users, "account", "accounts")}
            {people.invites ? `, ${plural(people.invites, "invitation", "invitations")}` : ""}.
          </p>
        ) : (
          <p>
            Create a lab and invite its members from it.{" "}
            <Link className="ws-link" href={appHref(SECTION_ROUTES.labs)}>
              Open labs <ArrowRight size={13} aria-hidden="true" />
            </Link>
          </p>
        ),
    },
    {
      key: "discord",
      state: discord.state,
      title: discord.state === "done" ? "Mylo is in Discord" : "Optional: Mylo in Discord",
      body:
        discord.state === "done" ? (
          <p>Installed in {plural(discord.servers, "server", "servers")}.</p>
        ) : (
          <p>
            Daily reports and questions in your lab&rsquo;s Discord server.{" "}
            {discord.bot_configured
              ? "The bot token is set; add Mylo to a server from a lab's settings."
              : "It needs a bot token in .env-mylo; docs/discord-integration.md in the repository walks through it."}
          </p>
        ),
    },
  ];
}

function StepList({ status }: { status: SetupStatus }) {
  const steps = useSteps(status);
  return (
    <ol className="m-0 flex list-none flex-col gap-3 p-0">
      {steps.map((step) => (
        <li key={step.key} className="flex gap-3" data-state={step.state}>
          <span className="mt-0.5 shrink-0">
            <StepIcon state={step.state} />
          </span>
          <div className="min-w-0 flex-1 text-[14px] leading-relaxed text-[var(--text-secondary)]">
            <h3 className="m-0 text-[15px] font-semibold text-[var(--text-primary)]">
              {step.title}
              <span className="sr-only"> ({stateLabel(step.state)})</span>
            </h3>
            {step.body}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** The checklist card, for staff. Renders nothing once the required steps are done. */
export function GettingStarted({ enabled }: { enabled: boolean }) {
  const query = useSetupStatus(enabled);
  if (!enabled) return null;
  if (query.isError && query.error instanceof ApiError && query.error.status === 403) return null;
  if (query.data?.complete) return null;

  const required = query.data
    ? (["model", "collection", "profile", "people"] as const).filter((key) =>
        ["done", "skipped"].includes(query.data.steps[key].state),
      ).length
    : 0;

  return (
    <section className="ws-panel-box ws-rise" aria-labelledby="getting-started-title">
      <div className="ws-panel-head">
        <h2 id="getting-started-title" className="ws-h ws-panel-title">
          Getting started
        </h2>
        {query.data ? <span className="ws-meta-text">{required} of 4 done</span> : null}
      </div>
      {query.isLoading ? (
        <LinesSkeleton rows={5} />
      ) : query.isError || !query.data ? (
        <div className="flex flex-wrap items-center gap-3 text-[14px] text-[var(--text-secondary)]">
          <p className="m-0">Could not load the setup checklist.</p>
          <button
            type="button"
            className="ws-link inline-flex items-center gap-1"
            onClick={() => void query.refetch()}
          >
            <RefreshCw size={13} aria-hidden="true" /> Try again
          </button>
        </div>
      ) : (
        <StepList status={query.data} />
      )}
    </section>
  );
}

/** What a member sees on an overview with nothing in it yet. */
export function NothingYet() {
  return (
    <section className="ws-panel-box ws-rise" aria-labelledby="nothing-yet-title">
      <div className="ws-panel-head">
        <h2 id="nothing-yet-title" className="ws-h ws-panel-title">
          Nothing here yet
        </h2>
      </div>
      <div className="text-[14px] leading-relaxed text-[var(--text-secondary)]">
        <p className="m-0">
          This instance has not collected any papers or opportunities yet. Once it runs its first collection,
          the ones that fit your profile appear here, and Mylo writes you a report each morning after that.
        </p>
        <p className="mb-0 mt-2">
          Meanwhile, the more your profile says about your research, the better the first lists will be. If
          nothing has appeared after a day, ask whoever runs this instance.
        </p>
      </div>
    </section>
  );
}
