import { ErrorBoundary } from "@/components/common";
import { FeedbackPage } from "@/components/feedback";
import { AppShell } from "@/components/layout/AppShell";

export default function FeedbackRoute() {
  return <AppShell><ErrorBoundary><FeedbackPage /></ErrorBoundary></AppShell>;
}
