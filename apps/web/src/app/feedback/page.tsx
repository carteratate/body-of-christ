import { ErrorBoundary } from "@/components/common";
import { FeedbackPage } from "@/components/feedback";

export default function FeedbackRoute() {
  return <ErrorBoundary><FeedbackPage /></ErrorBoundary>;
}
