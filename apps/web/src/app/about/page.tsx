import { AppShell } from "@/components/layout/AppShell";
import { AboutPage } from "@/components/about/AboutPage";

export const metadata = { title: "About — Body of Christ" };

export default function AboutRoute() {
  return (
    <AppShell>
      <AboutPage />
    </AppShell>
  );
}
