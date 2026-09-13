"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import {
  countryLabel,
  institutionCaption,
  institutionForEmail,
  isDirectoryName,
  loadInstitutions,
  searchInstitutions,
  type Institution,
  type InstitutionDirectory,
  type InstitutionMatch,
} from "@/lib/institutions";
import { cn } from "@/lib/utils";

const DEFAULT_INPUT_CLASS =
  "w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 pr-16 text-sm text-foreground outline-none transition placeholder:text-[var(--text-muted)] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

/** A row in the open list. `custom` is the reader's own text; `suggestion` is
 *  what their email address implies before they have typed anything. */
type Row =
  | { kind: "match"; match: InstitutionMatch }
  | { kind: "suggestion"; institution: Institution }
  | { kind: "custom"; text: string };

function rowInstitution(row: Row): Institution | null {
  if (row.kind === "custom") {
    return null;
  }
  return row.kind === "suggestion" ? row.institution : row.match.institution;
}

function rowName(row: Row): string {
  return row.kind === "custom" ? row.text : rowInstitution(row)?.name ?? "";
}

/**
 * Choose an affiliation from the directory — or type one the directory has
 * never heard of.
 *
 * Why not a `<select>`. The directory is ~10,300 entries. A native select
 * renders it, but nobody can use it: no filtering, a scroll list several
 * screens tall on a phone, and a paint cost for a control most readers touch
 * once. This is the ARIA combobox pattern instead — a text input that filters
 * as you type, with the list as a `listbox` beside it.
 *
 * Why "Custom" is not a menu item. National labs, government agencies,
 * teaching hospitals, industry research groups and newly renamed universities
 * are all affiliations a community-maintained university list does not carry,
 * and a reader at one of them is not an edge case to be pushed down a side
 * path. So the input is *always* the field: whatever is typed is the value,
 * committed on every keystroke exactly as the plain text input this replaces
 * did. Picking a row fills it in; ignoring the list entirely leaves what you
 * wrote. The last row states that plainly ("Use …, not in the directory") so
 * the behaviour is visible rather than merely true.
 *
 * Consequence worth knowing: nothing here is validated against the directory.
 * `Profile.institution` stays a free string — `onSelect` reports the matched
 * row (with its country and email domain) when there is one and `null` when
 * the reader wrote their own, for callers that want the extra detail.
 */
export function InstitutionPicker({
  id,
  value,
  onChange,
  onSelect,
  email,
  disabled = false,
  placeholder = "Search universities, labs and institutes",
  className,
  inputClassName,
  describedBy,
  limit = 8,
}: {
  id: string;
  /** The affiliation as stored: a plain name string, picked or typed. */
  value: string;
  onChange: (next: string) => void;
  /** The directory row behind the change, or null when it was free text. */
  onSelect?: (institution: Institution | null) => void;
  /** The reader's email, if known. Its domain seeds the first suggestion. */
  email?: string;
  disabled?: boolean;
  placeholder?: string;
  /** Wrapper — needs to establish a positioning context for the list. */
  className?: string;
  /** The input's own look, so each surface keeps its field styling. */
  inputClassName?: string;
  describedBy?: string;
  limit?: number;
}) {
  const listId = `${id}-listbox`;
  const statusId = `${id}-status`;

  const [directory, setDirectory] = React.useState<InstitutionDirectory | null>(null);
  const [state, setState] = React.useState<"idle" | "loading" | "ready" | "error">("idle");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  /** What is in the box. Mirrors `value`, and is the value while typing. */
  const [query, setQuery] = React.useState(value);

  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const listRef = React.useRef<HTMLUListElement>(null);
  /** Where to put the list, in viewport coordinates. See `position`. */
  const [box, setBox] = React.useState<{
    left: number;
    top: number;
    width: number;
    maxHeight: number;
  } | null>(null);

  /**
   * Measure the field and place the list against it.
   *
   * The list is portalled to `<body>` and positioned by hand rather than
   * absolutely inside the field's wrapper, because every surface that asks for
   * an affiliation clips: the onboarding step card, the profile editor modal's
   * scrolling panel, the department dialog. An absolutely positioned list is
   * cut off by the first ancestor with `overflow: hidden`, which is not a thing
   * this component can see or fix from inside. Fixed coordinates opt out of
   * that whole question, at the cost of having to re-measure on scroll and
   * resize — which is what the listener below does.
   *
   * It also flips above the field when there is more room up there, so the list
   * is never a two-row sliver at the bottom of a phone screen.
   */
  const position = React.useCallback(() => {
    const input = inputRef.current;
    if (!input) {
      return;
    }
    const rect = input.getBoundingClientRect();
    const gap = 6;
    const margin = 12;
    const below = window.innerHeight - rect.bottom - gap - margin;
    const above = rect.top - gap - margin;
    const ceiling = Math.min(320, Math.max(window.innerHeight * 0.5, 180));
    const openUp = below < Math.min(ceiling, 220) && above > below;
    const maxHeight = Math.max(120, Math.min(ceiling, openUp ? above : below));
    setBox({
      left: rect.left,
      top: openUp ? rect.top - gap - maxHeight : rect.bottom + gap,
      width: rect.width,
      maxHeight,
    });
  }, []);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    position();
    const onMove = () => position();
    // `capture` so a scroll inside the modal's own panel counts, not just the
    // window's.
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open, position]);

  // An external edit (a form reset, a profile finishing its load) wins over
  // stale local text, but never yanks the box out from under someone typing.
  React.useEffect(() => {
    if (document.activeElement !== inputRef.current) {
      setQuery(value);
    }
  }, [value]);

  /** Load on first interaction, not on mount: most readers never touch this
   *  field, and 160 KB is not worth spending on the ones who don't. */
  const ensureLoaded = React.useCallback(() => {
    if (state !== "idle") {
      return;
    }
    setState("loading");
    loadInstitutions().then(
      (loaded) => {
        setDirectory(loaded);
        setState("ready");
      },
      () => setState("error"),
    );
  }, [state]);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      // The list is portalled out of the wrapper, so it needs checking too.
      if (
        !wrapperRef.current?.contains(target) &&
        !listRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const trimmed = query.trim();

  const rows = React.useMemo<Row[]>(() => {
    if (!directory) {
      return [];
    }
    if (!trimmed) {
      // Nothing typed yet. If their address says where they work, offer it —
      // one row, clearly labelled, not a pre-filled field they have to notice.
      const suggested = email ? institutionForEmail(directory, email) : null;
      return suggested && suggested.name !== value
        ? [{ kind: "suggestion", institution: suggested }]
        : [];
    }
    const matches = searchInstitutions(directory, trimmed, limit);
    const out: Row[] = matches.map((match) => ({ kind: "match", match }));
    if (!isDirectoryName(directory, trimmed)) {
      out.push({ kind: "custom", text: trimmed });
    }
    return out;
  }, [directory, email, limit, trimmed, value]);

  // `active` is stored raw and clamped here rather than reset from an effect:
  // the row count changes on every keystroke, and a cursor past the end of a
  // shorter list should simply sit on its last row.
  const activeIndex = rows.length === 0 ? 0 : Math.min(active, rows.length - 1);

  // A list that just grew or shrank may no longer fit where it was placed.
  React.useEffect(() => {
    if (open) {
      position();
    }
  }, [open, position, rows.length, state]);

  // Keep the highlighted row on screen while arrowing through a long list.
  React.useEffect(() => {
    if (!open || !listRef.current) {
      return;
    }
    listRef.current
      .querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  function commit(row: Row) {
    const name = rowName(row);
    setQuery(name);
    onChange(name);
    onSelect?.(rowInstitution(row));
    setOpen(false);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      if (open) {
        event.stopPropagation();
        setOpen(false);
      }
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      ensureLoaded();
      if (!open) {
        setOpen(true);
        return;
      }
      if (rows.length === 0) {
        return;
      }
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((activeIndex + step + rows.length) % rows.length);
      return;
    }
    if (event.key === "Home" && open && rows.length > 0) {
      event.preventDefault();
      setActive(0);
      return;
    }
    if (event.key === "End" && open && rows.length > 0) {
      event.preventDefault();
      setActive(rows.length - 1);
      return;
    }
    if (event.key === "Enter" && open && rows[activeIndex]) {
      // Only swallow the submit when the list actually has a choice under the
      // cursor; a plain Enter on typed text should still submit the form.
      event.preventDefault();
      commit(rows[activeIndex]);
    }
  }

  const status =
    state === "loading"
      ? "Loading the affiliation directory…"
      : state === "error"
        ? "The directory could not be loaded. Type your affiliation instead."
        : !trimmed
          ? rows.length > 0
            ? "One suggestion from your email address."
            : "Type to search universities, labs and institutes."
          : rows.length === 0
            ? "No match — what you type is kept as written."
            : `${rows.length} result${rows.length === 1 ? "" : "s"}.`;

  return (
    <div className={cn("relative", className)} ref={wrapperRef}>
      <input
        id={id}
        ref={inputRef}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={
          open && rows[activeIndex] ? `${id}-row-${activeIndex}` : undefined
        }
        aria-describedby={[describedBy, statusId].filter(Boolean).join(" ") || undefined}
        placeholder={placeholder}
        disabled={disabled}
        value={query}
        className={cn(inputClassName ?? DEFAULT_INPUT_CLASS, "pr-16")}
        onFocus={ensureLoaded}
        onChange={(event) => {
          const next = event.target.value;
          setQuery(next);
          setActive(0);
          // Committed as typed: this field was a plain text input, and a reader
          // who never opens the list must still end up with what they wrote.
          onChange(next);
          ensureLoaded();
          setOpen(true);
        }}
        onClick={() => {
          ensureLoaded();
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />

      <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
        {query && !disabled ? (
          <button
            type="button"
            aria-label="Clear affiliation"
            className="flex size-7 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-surface-alt hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => {
              setQuery("");
              setActive(0);
              onChange("");
              onSelect?.(null);
              setOpen(true);
              inputRef.current?.focus();
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        ) : null}
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          disabled={disabled}
          className="flex size-7 items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-surface-alt disabled:opacity-40"
          onClick={() => {
            ensureLoaded();
            setOpen((current) => !current);
            inputRef.current?.focus();
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d={open ? "m6 15 6-6 6 6" : "m6 9 6 6 6-6"} />
          </svg>
        </button>
      </div>

      {/* The one announcement a screen-reader user needs: how many results the
          last keystroke produced, and that free text is acceptable. */}
      <p className="sr-only" id={statusId} role="status" aria-live="polite">
        {open ? status : ""}
      </p>

      {open && box
        ? createPortal(
            <ul
              ref={listRef}
              id={listId}
              role="listbox"
              aria-label="Affiliations"
              style={{
                left: box.left,
                top: box.top,
                width: box.width,
                maxHeight: box.maxHeight,
              }}
              className="fixed z-50 overflow-y-auto overscroll-contain rounded-xl border border-border bg-surface py-1 shadow-lg"
            >
              {state === "loading" ? (
                <li className="px-3.5 py-3 text-sm text-[var(--text-muted)]">
                  Loading directory…
                </li>
              ) : null}

              {state === "error" ? (
                <li className="px-3.5 py-3 text-sm text-[var(--text-secondary)]">
                  The directory could not be loaded — type your affiliation and it
                  will be saved as written.
                </li>
              ) : null}

              {state === "ready" && rows.length === 0 ? (
                <li className="px-3.5 py-3 text-sm text-[var(--text-muted)]">
                  {trimmed
                    ? "No match in the directory. What you typed will be saved as written."
                    : "Start typing a university, national lab or institute."}
                </li>
              ) : null}

              {rows.map((row, index) => {
                const selected = rowName(row) === value;
                return (
                  <li
                    key={`${row.kind}-${rowName(row)}-${index}`}
                    id={`${id}-row-${index}`}
                    data-index={index}
                    role="option"
                    aria-selected={selected}
                    className={cn(
                      "cursor-pointer px-3.5 py-2.5",
                      index === activeIndex && "bg-surface-alt",
                    )}
                    // Pointer down, not click: a click fires after the input's
                    // blur would have closed the list on some browsers.
                    onMouseDown={(event) => {
                      event.preventDefault();
                      commit(row);
                    }}
                    onMouseEnter={() => setActive(index)}
                  >
                    <RowBody row={row} selected={selected} />
                  </li>
                );
              })}
            </ul>,
            document.body,
          )
        : null}
    </div>
  );
}

function RowBody({ row, selected }: { row: Row; selected: boolean }) {
  if (row.kind === "custom") {
    return (
      <div className="flex items-start gap-2">
        <svg
          className="mt-0.5 flex-none text-[var(--text-muted)]"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
            Use “{row.text}”
          </span>
          <span className="mt-0.5 block text-xs text-[var(--text-muted)]">
            Not in the directory — saved exactly as you typed it
          </span>
        </span>
      </div>
    );
  }

  const institution = rowInstitution(row)!;
  const highlight = row.kind === "match" ? row.match.highlight : null;

  return (
    <div className="flex items-start gap-2">
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium text-[var(--text-primary)]">
            <Emphasized text={institution.name} range={highlight} />
          </span>
          {institution.kind === "institute" ? (
            <span className="flex-none rounded-full border border-border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
              Institute
            </span>
          ) : null}
          {selected ? (
            <svg
              className="flex-none text-primary"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              aria-hidden="true"
            >
              <path d="m5 13 4 4L19 7" />
            </svg>
          ) : null}
        </span>
        <span className="mt-0.5 block truncate text-xs text-[var(--text-muted)]">
          {row.kind === "suggestion"
            ? `Suggested from your email · ${countryLabel(institution.countryCode)}`
            : institutionCaption(institution)}
        </span>
      </span>
    </div>
  );
}

/** The matched fragment in bold, so a long name shows why it is in the list.
 *  Emphasis only — never the sole carrier of meaning. */
function Emphasized({
  text,
  range,
}: {
  text: string;
  range: [number, number] | null;
}) {
  if (!range) {
    return <>{text}</>;
  }
  const [start, end] = range;
  return (
    <>
      {text.slice(0, start)}
      <strong className="font-semibold text-[var(--text-primary)] underline decoration-primary/50 decoration-2 underline-offset-2">
        {text.slice(start, end)}
      </strong>
      {text.slice(end)}
    </>
  );
}
