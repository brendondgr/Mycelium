import { SettingsShell } from "@/components/portal/settings-shell";
import { MembersSection } from "@/components/portal/sections/members-section";

export const metadata = { title: "Members · Mycelium" };

export default function MembersPage() {
  return (
    <SettingsShell current="members">
      <MembersSection />
    </SettingsShell>
  );
}
