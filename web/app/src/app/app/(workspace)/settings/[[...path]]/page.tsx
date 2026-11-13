import { SettingsArea } from "@/components/portal/settings/settings-area";

export const metadata = { title: "Settings · Mycelium" };

// The context and page are read from the path inside the (client) area, the
// same way the project detail page drives itself from the URL.
export default function SettingsPage() {
  return <SettingsArea />;
}
