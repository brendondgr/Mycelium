"use client";

import * as React from "react";
import { Monitor, PanelRightOpen, Smartphone, Tablet } from "lucide-react";

import { ControlPanel } from "@/components/labs/control-panel";
import { PreviewApp } from "@/components/labs/preview/preview-app";
import { defaultState, mergeState, type LabsState, type PageKey } from "@/components/labs/schema";

const STORAGE_KEY = "mycelium-labs-v1";
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
  const [state, setState] = React.useState<LabsState>(() =>
    mergeState(readJson<Partial<LabsState>>(STORAGE_KEY)),
  );
  const [view] = React.useState(() => readJson<{ device?: Device; panelOpen?: boolean }>(VIEW_KEY));
  const [device, setDevice] = React.useState<Device>(view?.device ?? "desktop");
  const [panelOpen, setPanelOpen] = React.useState(view?.panelOpen ?? true);

  React.useEffect(() => writeJson(STORAGE_KEY, state), [state]);
  React.useEffect(() => writeJson(VIEW_KEY, { device, panelOpen }), [device, panelOpen]);

  const update = React.useCallback((fn: (s: LabsState) => LabsState) => setState(fn), []);
  const setPage = React.useCallback((page: PageKey) => setState((s) => ({ ...s, page })), []);

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
            <PreviewApp state={state} setPage={setPage} />
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
