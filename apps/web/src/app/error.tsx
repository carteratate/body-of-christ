"use client";

import { useEffect } from "react";
import { PageErrorState } from "@/components/common/PageStates";
import { trackErrorOccurred } from "@/lib/analytics";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    trackErrorOccurred({ page: "route", errorType: "render_error" });
  }, []);

  return <PageErrorState reset={reset} />;
}
