"use client";

import { Palette } from "lucide-react";

import { usePortal } from "@/components/portal/portal-context";
import { useAppearance, type Density, type Motion } from "@/lib/portal/appearance";

function Seg<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="ws-form-row">
      <span className="ws-form-label">{label}</span>
      <span className="ws-chips" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            className="ws-chip"
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </span>
    </div>
  );
}

/** Theme, density and motion — applied across the whole workspace at once. */
export function AppearanceCard() {
  const { theme, toggleTheme } = usePortal();
  const { density, motion, setDensity, setMotion } = useAppearance();
  return (
    <section id="appearance" className="ws-panel-box ws-settings-section" aria-labelledby="appearance-title">
      <h2 id="appearance-title" className="ws-h ws-panel-title">
        <Palette size={16} aria-hidden="true" className="mr-2 inline-block align-[-2px]" />
        Appearance
      </h2>
      <p className="ws-meta-text">
        Stored in this browser, not on your account: it applies to every page on
        this device, and another device keeps its own.
      </p>
      <Seg
        label="Theme"
        value={theme}
        onChange={(v) => v !== theme && toggleTheme()}
        options={[
          { value: "dark", label: "Night Forest" },
          { value: "light", label: "Daylight" },
        ]}
      />
      <Seg<Density>
        label="Density"
        value={density}
        onChange={setDensity}
        options={[
          { value: "compact", label: "Compact" },
          { value: "comfortable", label: "Comfortable" },
          { value: "open", label: "Open" },
        ]}
      />
      <Seg<Motion>
        label="Motion"
        value={motion}
        onChange={setMotion}
        options={[
          { value: "full", label: "Full" },
          { value: "subtle", label: "Subtle" },
          { value: "none", label: "None" },
        ]}
      />
    </section>
  );
}
