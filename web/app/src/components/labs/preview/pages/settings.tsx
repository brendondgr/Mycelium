"use client";

import * as React from "react";
import {
  Bell,
  Building2,
  Link2,
  Palette,
  ShieldCheck,
  Sparkles,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { OptionValue } from "@/components/labs/schema";
import { MEMBERS, THEMES } from "@/components/labs/preview/fixtures";
import { MyloMark, PageHead, ThemeTag } from "@/components/labs/preview/parts";

type SectionKey = "account" | "notifications" | "mylo" | "appearance" | "lab" | "members" | "integrations";

const SECTIONS: { key: SectionKey; label: string; group: string; icon: LucideIcon; blurb: string }[] = [
  { key: "account", label: "Account", group: "You", icon: UserRound, blurb: "Name, email, password" },
  { key: "notifications", label: "Notifications", group: "You", icon: Bell, blurb: "Report, reminders, Discord" },
  { key: "mylo", label: "Mylo & you", group: "You", icon: Sparkles, blurb: "What Mylo knows and asks" },
  { key: "appearance", label: "Appearance", group: "You", icon: Palette, blurb: "Theme and density" },
  { key: "lab", label: "Pulse Lab", group: "Lab", icon: Building2, blurb: "Themes, profile, announcements" },
  { key: "members", label: "Members", group: "Lab", icon: Users, blurb: "Roles and invitations" },
  { key: "integrations", label: "Integrations", group: "Lab", icon: Link2, blurb: "Discord servers and channels" },
];

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="lx-form-row">
      <span>
        <span className="lx-form-label">{label}</span>
        {hint ? <span className="lx-form-hint">{hint}</span> : null}
      </span>
      <span className="lx-form-control">{children}</span>
    </div>
  );
}

function Switch({ label, defaultOn = false }: { label: string; defaultOn?: boolean }) {
  const [on, setOn] = React.useState(defaultOn);
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className="lx-switch" onClick={() => setOn((v) => !v)}>
      <span aria-hidden="true" />
    </button>
  );
}

function Seg({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <span className="lx-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </span>
  );
}

function SectionBody({
  k,
  g,
  setGlobal,
}: {
  k: SectionKey;
  g: Record<string, OptionValue>;
  setGlobal: (id: string, v: OptionValue) => void;
}) {
  const [cadence, setCadence] = React.useState("daily");
  switch (k) {
    case "account":
      return (
        <>
          <Row label="Name">
            <input className="lx-input" defaultValue="Ama Owusu" aria-label="Name" />
          </Row>
          <Row label="Email" hint="Verified — your institution comes from it">
            <span className="lx-readonly">
              <ShieldCheck size={14} aria-hidden="true" /> ama.owusu@university.edu
            </span>
          </Row>
          <Row label="Institution">
            <span className="lx-readonly">State University</span>
          </Row>
          <Row label="Password">
            <button type="button" className="lx-btn lx-btn-line lx-btn-sm">
              Change password
            </button>
          </Row>
        </>
      );
    case "notifications":
      return (
        <>
          <Row label="Morning report" hint="When the report reaches you outside the app">
            <Seg
              label="Report cadence"
              value={cadence}
              onChange={setCadence}
              options={[
                { value: "daily", label: "Daily" },
                { value: "weekly", label: "Weekly" },
                { value: "off", label: "Off" },
              ]}
            />
          </Row>
          <Row label="Email the report">
            <Switch label="Email the report" defaultOn />
          </Row>
          <Row label="Discord DMs for deadlines" hint="7 days and 1 day before">
            <Switch label="Discord DMs for deadlines" defaultOn />
          </Row>
          <Row label="Tell me when someone saves to the lab">
            <Switch label="Tell me when someone saves to the lab" />
          </Row>
        </>
      );
    case "mylo":
      return (
        <>
          <div className="lx-note lx-note-quiet">
            <MyloMark size={28} />
            <p className="lx-note-text">
              I know your four themes, two projects and 31 saved items. I ask before I change anything about you.
            </p>
          </div>
          <Row label="Your themes">
            <span className="lx-theme-row">
              {THEMES.slice(1, 3).map((t) => (
                <ThemeTag key={t.id} id={t.id} />
              ))}
            </span>
          </Row>
          <Row label="Let Mylo ask questions" hint="Like “Is this project still active?”">
            <Switch label="Let Mylo ask questions" defaultOn />
          </Row>
          <Row label="Learn from what I save and hide">
            <Switch label="Learn from what I save and hide" defaultOn />
          </Row>
        </>
      );
    case "appearance":
      return (
        <>
          <Row label="Theme" hint="Changes the Labs option too">
            <Seg
              label="Theme"
              value={g.theme as string}
              onChange={(v) => setGlobal("theme", v)}
              options={[
                { value: "night", label: "Night Forest" },
                { value: "day", label: "Daylight" },
              ]}
            />
          </Row>
          <Row label="Density">
            <Seg
              label="Density"
              value={g.density as string}
              onChange={(v) => setGlobal("density", v)}
              options={[
                { value: "compact", label: "Compact" },
                { value: "comfortable", label: "Comfortable" },
                { value: "open", label: "Open" },
              ]}
            />
          </Row>
          <Row label="Motion">
            <Seg
              label="Motion"
              value={g.motion as string}
              onChange={(v) => setGlobal("motion", v)}
              options={[
                { value: "full", label: "Full" },
                { value: "subtle", label: "Subtle" },
                { value: "none", label: "None" },
              ]}
            />
          </Row>
        </>
      );
    case "lab":
      return (
        <>
          <Row label="Lab name">
            <input className="lx-input" defaultValue="Pulse Lab" aria-label="Lab name" />
          </Row>
          <Row label="Research themes" hint="What every lab feed is ranked against">
            <span className="lx-theme-row">
              {THEMES.map((t) => (
                <ThemeTag key={t.id} id={t.id} />
              ))}
            </span>
          </Row>
          <Row label="Announce new items in Discord" hint="Posts to #grants and #papers">
            <Switch label="Announce new items in Discord" defaultOn />
          </Row>
          <Row label="Who may change these">
            <span className="lx-readonly">Owners and admins</span>
          </Row>
        </>
      );
    case "members":
      return (
        <>
          <ul className="lx-person-list">
            {MEMBERS.map((m) => (
              <li key={m.id}>
                <span className="lx-avatar-sm lx-avatar-md" aria-hidden="true">
                  {m.initials}
                </span>
                <span className="lx-person-body">
                  <span className="lx-person">{m.name}</span>
                  <span className="lx-meta-text">{m.role}</span>
                </span>
                <span className="lx-pill">{m.role === "PI" ? "Owner" : "Member"}</span>
              </li>
            ))}
          </ul>
          <button type="button" className="lx-btn lx-btn-solid lx-btn-sm">
            Invite people
          </button>
        </>
      );
    case "integrations":
      return (
        <>
          <Row label="Discord server" hint="Pulse Lab · 3 channels bound">
            <span className="lx-readonly">
              <ShieldCheck size={14} aria-hidden="true" /> Connected
            </span>
          </Row>
          <Row label="Papers channel">
            <span className="lx-readonly">#papers</span>
          </Row>
          <Row label="Grants channel">
            <span className="lx-readonly">#grants</span>
          </Row>
        </>
      );
  }
}

export function SettingsPage({
  o,
  g,
  setGlobal,
  initial = "account",
}: {
  o: Record<string, OptionValue>;
  g: Record<string, OptionValue>;
  setGlobal: (id: string, v: OptionValue) => void;
  initial?: string;
}) {
  const [open, setOpen] = React.useState<SectionKey>(
    SECTIONS.some((s) => s.key === initial) ? (initial as SectionKey) : "account",
  );
  const single = o.layout === "single";
  const groups = Array.from(new Set(SECTIONS.map((s) => s.group)));
  const current = SECTIONS.find((s) => s.key === open)!;

  if (single) {
    return (
      <div className="lx-settings" data-layout="single">
        <PageHead title="Settings" lede="Everything about you and Pulse Lab, on one page." />
        <nav className="lx-chips lx-chips-wrap lx-rise" aria-label="Jump to">
          {SECTIONS.map((s) => (
            <a key={s.key} className="lx-chip" href={`#lx-set-${s.key}`}>
              {s.label}
            </a>
          ))}
        </nav>
        {SECTIONS.map((s) => (
          <section key={s.key} id={`lx-set-${s.key}`} className="lx-panel-box lx-settings-section lx-rise">
            <h2 className="lx-h lx-panel-title">{s.label}</h2>
            <p className="lx-meta-text">{s.blurb}</p>
            <SectionBody k={s.key} g={g} setGlobal={setGlobal} />
          </section>
        ))}
      </div>
    );
  }

  return (
    <div className="lx-settings" data-layout="sectioned">
      <PageHead title="Settings" lede="Everything about you and Pulse Lab." />
      <div className="lx-settings-grid">
        <nav className="lx-settings-nav lx-rise" aria-label="Settings sections">
          {groups.map((grp) => (
            <div key={grp} className="lx-nav-group">
              <p className="lx-nav-label">{grp}</p>
              {SECTIONS.filter((s) => s.group === grp).map((s) => {
                const Icon = s.icon;
                return (
                  <button
                    key={s.key}
                    type="button"
                    className="lx-nav-item"
                    aria-current={open === s.key ? "page" : undefined}
                    onClick={() => setOpen(s.key)}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span className="lx-nav-text">
                      {s.label}
                      <span className="lx-nav-blurb">{s.blurb}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <section key={open} className="lx-panel-box lx-settings-section lx-rise" aria-label={current.label}>
          <h2 className="lx-h lx-panel-title">{current.label}</h2>
          <p className="lx-meta-text">{current.blurb}</p>
          <SectionBody k={open} g={g} setGlobal={setGlobal} />
        </section>
      </div>
    </div>
  );
}
