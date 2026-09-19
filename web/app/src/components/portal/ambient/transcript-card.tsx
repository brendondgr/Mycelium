"use client";

import * as React from "react";

import { Card } from "@/components/portal/primitives/card";
import { useAmbientSettings } from "@/lib/portal/ambient/hooks";
import {
  type TranscriptPreview,
  type TranscriptRead,
  uploadTranscript,
} from "@/lib/portal/ambient/slack";

/**
 * A meeting transcript for this project (ambient Plan 11). Upload it, say who
 * each speaker was, and Mylo reads it once. Only the turns of members who
 * opted in to transcripts are read, only the project's decisions and blockers
 * are kept, and the transcript itself is not kept. Hidden while transcripts
 * are off.
 */
export function TranscriptCard({ projectId }: { projectId: string }) {
  const settings = useAmbientSettings();
  const [file, setFile] = React.useState<File | null>(null);
  const [title, setTitle] = React.useState("");
  const [when, setWhen] = React.useState("");
  const [preview, setPreview] = React.useState<TranscriptPreview | null>(null);
  const [mapping, setMapping] = React.useState<Record<string, string>>({});
  const [result, setResult] = React.useState<TranscriptRead | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  if (!settings.data?.transcripts) return null;

  const form = (withSpeakers: boolean) => {
    const body = new FormData();
    if (file) body.append("file", file);
    body.append("project", projectId);
    body.append("title", title || "Meeting");
    if (withSpeakers) {
      body.append("occurred_at", when ? new Date(when).toISOString() : "");
      const speakers: Record<string, number> = {};
      for (const [label, id] of Object.entries(mapping)) if (id) speakers[label] = Number(id);
      body.append("speakers", JSON.stringify(speakers));
    }
    return body;
  };

  const run = async (withSpeakers: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const reply = await uploadTranscript(form(withSpeakers));
      if ("labels" in reply) setPreview(reply);
      else setResult(reply);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That didn't go through.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-[18px]" data-ambient="transcript">
      <h2 className="text-[12px] font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)]">
        Add a meeting transcript
      </h2>
      <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
        Mylo reads it once for this project&apos;s decisions and blockers. Only members who opted
        in to transcripts are read, and the transcript itself is not kept.
      </p>
      {result ? (
        <p role="status" className="mt-3 text-sm text-[var(--text-primary)]">
          Read {result.counts.stored ?? 0} of {result.turns} turns; everyone named will be told.
        </p>
      ) : preview ? (
        <div className="mt-3 space-y-2">
          {preview.labels.map((label) => (
            <label key={label} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="min-w-[8rem] font-medium text-[var(--text-primary)]">{label}</span>
              <select
                value={mapping[label] ?? ""}
                onChange={(event) => setMapping((m) => ({ ...m, [label]: event.target.value }))}
                className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
              >
                <option value="">Not a member — skip</option>
                {preview.members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label className="block text-sm text-[var(--text-primary)]">
            <span className="block text-xs text-[var(--text-secondary)]">When the meeting was</span>
            <input
              type="datetime-local"
              value={when}
              onChange={(event) => setWhen(event.target.value)}
              className="mt-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            />
          </label>
          <button
            type="button"
            disabled={busy || !when}
            onClick={() => void run(true)}
            className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-[#fffdf8] disabled:opacity-60"
          >
            Read the transcript
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="block text-xs text-[var(--text-secondary)]">Transcript (.vtt, .srt, .txt)</span>
            <input
              type="file"
              accept=".vtt,.srt,.txt,text/plain,text/vtt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="mt-1 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="block text-xs text-[var(--text-secondary)]">Title</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              className="mt-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            />
          </label>
          <button
            type="button"
            disabled={busy || !file}
            onClick={() => void run(false)}
            className="rounded-lg border border-border px-3.5 py-2 text-sm font-medium text-[var(--text-primary)] hover:bg-surface-alt disabled:opacity-60"
          >
            Who was who?
          </button>
        </div>
      )}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-clay">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
