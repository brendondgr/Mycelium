import { SettingsShell } from "@/components/portal/settings-shell";
import { AccountSection } from "@/components/portal/sections/account-section";

export const metadata = { title: "Account · Mycelium" };

export default function AccountPage() {
  return (
    <SettingsShell current="account">
      <AccountSection />
    </SettingsShell>
  );
}
