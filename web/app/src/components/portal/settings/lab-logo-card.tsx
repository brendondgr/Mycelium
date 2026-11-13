"use client";

import * as React from "react";

import { CloseIcon } from "@/components/portal/icons";
import { Card } from "@/components/portal/primitives/card";
import { labLogoUrl } from "@/lib/portal/client";
import { useDeleteLabLogo, useUploadLabLogo } from "@/lib/portal/hooks";
import type { MyLab } from "@/lib/portal/types";
import { cn } from "@/lib/utils";

const GHOST_BUTTON =
  "rounded-full border border-border bg-surface px-4 py-2 text-[12.5px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
const PRIMARY_BUTTON =
  "inline-flex items-center gap-[7px] rounded-full bg-primary px-4 py-[9px] text-[13px] font-semibold text-[#fffdf8] transition-colors hover:bg-[var(--brand-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

const ACCEPT = ".png,.jpg,.jpeg,.gif,.webp,.svg,image/png,image/jpeg,image/gif,image/webp,image/svg+xml";
const MAX_BYTES = 2 * 1024 * 1024;

/** Upload, preview, or remove the lab's logo — shown as its workspace brand mark. */
export function LabLogoCard({ lab }: { lab: MyLab }) {
  const upload = useUploadLabLogo(lab.slug);
  const remove = useDeleteLabLogo(lab.slug);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [error, setError] = React.useState<string | null>(null);

  const src = labLogoUrl(lab.slug, lab.logo_version);
  const busy = upload.isPending || remove.isPending;

  function onFile(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError("The logo must be 2 MB or smaller.");
      return;
    }
    upload.mutate(file, { onError: (e) => setError((e as Error).message) });
  }

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">
        Lab logo
      </h2>
      <div className="flex flex-wrap items-center gap-4">
        <div
          className={cn(
            "flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-surface-alt",
          )}
        >
          {src ? (
            // The logo is served from our own API; a plain img is right here.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt={`${lab.name} logo`}
              className="h-full w-full object-contain"
            />
          ) : (
            <span className="font-serif text-[15px] font-semibold text-[var(--text-secondary)]">
              {lab.name.slice(0, 2).toUpperCase()}
            </span>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={PRIMARY_BUTTON}
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              {upload.isPending
                ? "Uploading…"
                : lab.has_logo
                  ? "Replace logo"
                  : "Upload logo"}
            </button>
            {lab.has_logo ? (
              <button
                type="button"
                className={GHOST_BUTTON}
                onClick={() => {
                  setError(null);
                  remove.mutate(undefined, {
                    onError: (e) => setError((e as Error).message),
                  });
                }}
                disabled={busy}
              >
                <span className="inline-flex items-center gap-1.5">
                  <CloseIcon size={13} />
                  Remove
                </span>
              </button>
            ) : null}
          </div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            PNG, JPG, GIF, WebP, or SVG · up to 2 MB. Shown in the sidebar as the
            lab&apos;s brand mark.
          </p>
          {error ? (
            <p className="text-[12.5px] text-clay" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        aria-label="Lab logo file"
        onChange={(e) => {
          onFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </Card>
  );
}
