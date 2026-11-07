import { SettingsShell } from "@/components/portal/settings-shell";
import { ProfileSection } from "@/components/portal/sections/profile-section";

export const metadata = { title: "Profile · Mycelium" };

export default function ProfilePage() {
  return (
    <SettingsShell current="profile">
      <ProfileSection />
    </SettingsShell>
  );
}
