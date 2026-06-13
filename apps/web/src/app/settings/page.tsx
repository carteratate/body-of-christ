import { AppShell } from "@/components/layout/AppShell";
import { SettingsPage } from "@/components/settings/SettingsPage";

export default function SettingsRoute() {
  return (
    <AppShell>
      <SettingsPage />
    </AppShell>
  );
}
