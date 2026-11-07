"use client";

import * as React from "react";
import { Monitor, PanelRightOpen, Smartphone, Tablet } from "lucide-react";

import { ControlPanel } from "@/components/labs/control-panel";
import { PreviewApp } from "@/components/labs/preview/preview-app";
import { defaultState, mergeState, type LabsState, type OptionValue, type PageKey } from "@/components/labs/schema";

const STORAGE_KEY = "mycelium-labs-v3";
const LEGACY_KEYS = ["mycelium-labs-v2", "mycelium-labs-v1"];
const VIEW_KEY = "mycelium-labs-view-v1";

type Device = "desktop" | "tablet" | "phone";

function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private window or blocked storage: the studio still works, it just
    // forgets on reload.
  }
}

/** The Overview's section list as it stood before v3 added four sections. */
const OLD_OVERVIEW_SECTIONS = ["note", "today", "closing", "found"];

/**
 * Saved choices, carried forward from an older version when that is all
 * there is. Each step changes only what the reviewer asked to change:
 *
 *   v1 → v2  Grants' board gave way to the list + reading pane.
 *   v2 → v3  The Overview gained its report, per-person, Mylo-asks and
 *            project panels; a section list still at the old default gets
 *            them, one someone edited by hand is left alone.
 */
function loadState(): LabsState {
  const current = readJson<Partial<LabsState>>(STORAGE_KEY);
  if (current) return mergeState(current);
  const [v2, v1] = LEGACY_KEYS.map((k) => readJson<Partial<LabsState>>(k));
  const legacy = v2 ?? v1;
  if (!legacy) return mergeState(null);
  const migrated = mergeState(legacy);
  if (!v2 && migrated.pages.grants.layout === "board") migrated.pages.grants.layout = "reader";
  const sections = migrated.pages.overview.sections as string[];
  if (sections.length === OLD_OVERVIEW_SECTIONS.length && OLD_OVERVIEW_SECTIONS.every((x) => sections.includes(x))) {
    migrated.pages.overview.sections = defaultState().pages.overview.sections;
  }
  return migrated;
}

/**
 * Mycelium Labs: a design playground for the authenticated workspace.
 *
 * The left is a working mock of the workspace, drawn from fictional data and
 * restyled after the Night Forest front page; the right is the panel of
 * options that reshape it. Choices persist in this browser only and leave as
 * one block of text via "Copy for Claude" — nothing here talks to the API.
 */
export function LabsStudio() {
  // The studio renders on the client only (see `labs-client.tsx`), so the
  // stored state can be read straight into the initial render.
  const [state, setState] = React.useState<LabsState>(loadState);
  const [view] = React.useState(() => readJson<{ device?: Device; panelOpen?: boolean }>(VIEW_KEY));
  const [device, setDevice] = React.useState<Device>(view?.device ?? "desktop");
  const [panelOpen, setPanelOpen] = React.useState(view?.panelOpen ?? true);

  React.useEffect(() => writeJson(STORAGE_KEY, state), [state]);
  React.useEffect(() => writeJson(VIEW_KEY, { device, panelOpen }), [device, panelOpen]);

  const update = React.useCallback((fn: (s: LabsState) => LabsState) => setState(fn), []);
  const setPage = React.useCallback((page: PageKey) => setState((s) => ({ ...s, page })), []);
  const setGlobal = React.useCallback(
    (id: string, value: OptionValue) => setState((s) => ({ ...s, global: { ...s.global, [id]: value } })),
    [],
  );

  const devices: { key: Device; label: string; icon: typeof Monitor }[] = [
    { key: "desktop", label: "Desktop", icon: Monitor },
    { key: "tablet", label: "Tablet", icon: Tablet },
    { key: "phone", label: "Phone", icon: Smartphone },
  ];

  return (
    <div className="lx-studio" data-panel={panelOpen ? "open" : "closed"}>
      <section className="lx-stage" aria-label="Preview">
        <div className="lx-stage-bar">
          <span className="lx-stage-title">
            Labs <span aria-hidden="true">·</span> <span className="lx-stage-page">{state.page}</span>
          </span>
          <div className="lx-devices" role="group" aria-label="Preview width">
            {devices.map((d) => {
              const Icon = d.icon;
              return (
                <button
                  key={d.key}
                  type="button"
                  aria-pressed={device === d.key}
                  aria-label={d.label}
                  title={d.label}
                  onClick={() => setDevice(d.key)}
                >
                  <Icon size={15} aria-hidden="true" />
                </button>
              );
            })}
          </div>
          {!panelOpen ? (
            <button type="button" className="lx-stage-open" onClick={() => setPanelOpen(true)}>
              <PanelRightOpen size={15} aria-hidden="true" /> Options
            </button>
          ) : null}
        </div>
        <div className="lx-frame-wrap">
          <div className="lx-frame" data-device={device}>
            <PreviewApp state={state} setPage={setPage} setGlobal={setGlobal} />
          </div>
        </div>
      </section>

      <aside className="lx-side" aria-label="Labs options" hidden={!panelOpen}>
        <ControlPanel
          state={state}
          update={update}
          reset={() => setState(defaultState())}
          onClose={() => setPanelOpen(false)}
        />
      </aside>
      {panelOpen ? (
        <button type="button" className="lx-side-scrim" aria-label="Hide the Labs panel" onClick={() => setPanelOpen(false)} />
      ) : null}
    </div>
  );
}
