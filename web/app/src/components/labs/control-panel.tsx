"use client";

import * as React from "react";
import { Check, ChevronDown, Copy, PanelRightClose, RotateCcw } from "lucide-react";

import {
  GLOBAL_OPTIONS,
  PAGES,
  VERDICTS,
  buildExport,
  changedCount,
  type LabsState,
  type OptionDef,
  type OptionValue,
  type PageKey,
} from "@/components/labs/schema";

function Field({
  def,
  value,
  onChange,
  name,
}: {
  def: OptionDef;
  value: OptionValue;
  onChange: (v: OptionValue) => void;
  name: string;
}) {
  const changed = Array.isArray(def.default)
    ? JSON.stringify([...(value as string[])].sort()) !== JSON.stringify([...def.default].sort())
    : value !== def.default;
  const label = (
    <span className="lc-label">
      {def.label}
      {changed ? <span className="lc-changed" title="Changed from the default">changed</span> : null}
    </span>
  );

  if (def.kind === "toggle") {
    return (
      <label className="lc-field lc-toggle-row">
        {label}
        <input
          type="checkbox"
          role="switch"
          className="lc-switch"
          checked={value as boolean}
          onChange={(e) => onChange(e.target.checked)}
        />
      </label>
    );
  }

  if (def.kind === "range") {
    return (
      <label className="lc-field">
        <span className="lc-range-head">
          {label}
          <span className="lc-range-value">
            {value as number}
            {def.unit}
          </span>
        </span>
        <input
          type="range"
          className="lc-range"
          min={def.min}
          max={def.max}
          step={def.step}
          value={value as number}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </label>
    );
  }

  if (def.kind === "multi") {
    const set = value as string[];
    return (
      <fieldset className="lc-field">
        <legend>{label}</legend>
        <div className="lc-multi">
          {def.choices.map((c) => (
            <label key={c.value} className="lc-check">
              <input
                type="checkbox"
                checked={set.includes(c.value)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? def.choices.map((x) => x.value).filter((v) => v === c.value || set.includes(v))
                      : set.filter((v) => v !== c.value),
                  )
                }
              />
              {c.label}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  // Short choices without hints read best as a segmented control; anything
  // that needs explaining gets a list with the hint under each choice.
  const segmented = def.choices.length <= 3 && def.choices.every((c) => !c.hint);
  return (
    <fieldset className="lc-field">
      <legend>{label}</legend>
      {def.help ? <p className="lc-help">{def.help}</p> : null}
      <div className={segmented ? "lc-seg" : "lc-choices"}>
        {def.choices.map((c) => (
          <label key={c.value} className={segmented ? "lc-seg-item" : "lc-choice"}>
            <input
              type="radio"
              name={name}
              value={c.value}
              checked={value === c.value}
              onChange={() => onChange(c.value)}
            />
            <span className="lc-choice-text">
              <span>{c.label}</span>
              {c.hint ? <span className="lc-hint">{c.hint}</span> : null}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API refused (insecure origin, permissions): fall back to a
    // selected textarea, which every browser still copies from.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

export function ControlPanel({
  state,
  update,
  reset,
  onClose,
}: {
  state: LabsState;
  update: (fn: (s: LabsState) => LabsState) => void;
  reset: () => void;
  onClose: () => void;
}) {
  const [globalOpen, setGlobalOpen] = React.useState(true);
  const [showExport, setShowExport] = React.useState(false);
  const [copied, setCopied] = React.useState<"idle" | "ok" | "fail">("idle");
  const page = PAGES.find((p) => p.key === state.page)!;
  const today = new Date().toISOString().slice(0, 10);
  const exportText = React.useMemo(() => buildExport(state, today), [state, today]);
  const changed = changedCount(state);

  const setPage = (key: PageKey) => update((s) => ({ ...s, page: key }));

  const doCopy = async () => {
    const ok = await copyText(exportText);
    setCopied(ok ? "ok" : "fail");
    if (!ok) setShowExport(true);
    window.setTimeout(() => setCopied("idle"), 2400);
  };

  return (
    <div className="lc-panel">
      <div className="lc-head">
        <div>
          <p className="lc-eyebrow">Mycelium Labs</p>
          <p className="lc-sub">
            {changed === 0 ? "All defaults" : `${changed} change${changed === 1 ? "" : "s"} from default`}
          </p>
        </div>
        <button type="button" className="lc-icon" aria-label="Hide the Labs panel" onClick={onClose}>
          <PanelRightClose size={17} aria-hidden="true" />
        </button>
      </div>

      <div className="lc-scroll">
        <div className="lc-pages" role="tablist" aria-label="Page to preview">
          {PAGES.map((p) => (
            <button
              key={p.key}
              type="button"
              role="tab"
              aria-selected={state.page === p.key}
              className="lc-page-tab"
              onClick={() => setPage(p.key)}
            >
              {p.label}
              {state.verdicts[p.key] ? <span className="lc-dot" data-verdict={state.verdicts[p.key]} aria-hidden="true" /> : null}
            </button>
          ))}
        </div>

        <section className="lc-section" aria-labelledby="lc-page-heading">
          <h2 id="lc-page-heading" className="lc-section-title">
            {page.label} <span className="lc-route">{page.route}</span>
          </h2>

          <fieldset className="lc-field">
            <legend>
              <span className="lc-label">How close is this page?</span>
            </legend>
            <div className="lc-seg">
              {VERDICTS.map((v) => (
                <label key={v.value} className="lc-seg-item" data-verdict={v.value}>
                  <input
                    type="radio"
                    name={`verdict-${page.key}`}
                    checked={state.verdicts[page.key] === v.value}
                    onChange={() => update((s) => ({ ...s, verdicts: { ...s.verdicts, [page.key]: v.value } }))}
                  />
                  <span className="lc-choice-text">
                    <span>{v.label}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {page.options.map((def) => (
            <Field
              key={`${page.key}-${def.id}`}
              name={`${page.key}-${def.id}`}
              def={def}
              value={state.pages[page.key][def.id]}
              onChange={(v) =>
                update((s) => ({
                  ...s,
                  pages: { ...s.pages, [page.key]: { ...s.pages[page.key], [def.id]: v } },
                }))
              }
            />
          ))}

          <label className="lc-field">
            <span className="lc-label">Notes on {page.label}</span>
            <textarea
              className="lc-notes"
              rows={4}
              placeholder="What works, what doesn't, what you'd want instead…"
              value={state.notes[page.key] ?? ""}
              onChange={(e) => update((s) => ({ ...s, notes: { ...s.notes, [page.key]: e.target.value } }))}
            />
          </label>
        </section>

        <section className="lc-section" aria-labelledby="lc-global-heading">
          <h2 className="lc-section-title">
            <button
              type="button"
              id="lc-global-heading"
              className="lc-disclosure"
              aria-expanded={globalOpen}
              onClick={() => setGlobalOpen((v) => !v)}
            >
              Everywhere
              <span className="lc-route">applies to every page</span>
              <ChevronDown size={15} aria-hidden="true" className="lc-caret" data-open={globalOpen || undefined} />
            </button>
          </h2>
          {globalOpen ? (
            <>
              {GLOBAL_OPTIONS.map((def) => (
                <Field
                  key={def.id}
                  name={`global-${def.id}`}
                  def={def}
                  value={state.global[def.id]}
                  onChange={(v) => update((s) => ({ ...s, global: { ...s.global, [def.id]: v } }))}
                />
              ))}
              <label className="lc-field">
                <span className="lc-label">Notes for the whole workspace</span>
                <textarea
                  className="lc-notes"
                  rows={4}
                  placeholder="Anything that applies across pages…"
                  value={state.notes.global}
                  onChange={(e) => update((s) => ({ ...s, notes: { ...s.notes, global: e.target.value } }))}
                />
              </label>
            </>
          ) : null}
        </section>

        {showExport ? (
          <section className="lc-section" aria-label="Export preview">
            <h2 className="lc-section-title">What gets copied</h2>
            <textarea className="lc-export" readOnly value={exportText} rows={14} onFocus={(e) => e.currentTarget.select()} />
          </section>
        ) : null}
      </div>

      <div className="lc-foot">
        <button type="button" className="lc-primary" onClick={doCopy}>
          {copied === "ok" ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {copied === "ok" ? "Copied" : "Copy for Claude"}
        </button>
        <button type="button" className="lc-secondary" aria-pressed={showExport} onClick={() => setShowExport((v) => !v)}>
          {showExport ? "Hide text" : "Show text"}
        </button>
        <button
          type="button"
          className="lc-icon"
          aria-label="Reset everything to defaults"
          title="Reset to defaults"
          onClick={() => {
            if (window.confirm("Reset every option, verdict and note to the defaults?")) reset();
          }}
        >
          <RotateCcw size={16} aria-hidden="true" />
        </button>
        <span className="lc-live" aria-live="polite">
          {copied === "fail" ? "Couldn't reach the clipboard — the text is shown above to copy by hand." : ""}
        </span>
      </div>
    </div>
  );
}
