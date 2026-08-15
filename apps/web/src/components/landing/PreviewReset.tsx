"use client";

import { useEffect } from "react";
import { clearGuestSession } from "@/lib/trial";

export function PreviewReset() {
  useEffect(() => { clearGuestSession(); }, []);
  return null;
}
