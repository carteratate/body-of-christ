"use client";

import { createContext, useContext } from "react";

/**
 * Guest-only signup gate. Provided by GuestShell; null under the authed AppShell.
 * When present, navigation actions (New Search, nav links) should call
 * `requestSignup()` to open the signup modal instead of navigating.
 */
export interface GuestGate {
  requestSignup: () => void;
}

export const GuestGateContext = createContext<GuestGate | null>(null);

/** Returns the guest gate when rendered inside GuestShell, otherwise null. */
export function useGuestGate(): GuestGate | null {
  return useContext(GuestGateContext);
}
