function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? match.split("=")[1] : null;
}

export function getTrialState(): "available" | "used" {
  return readCookie("tc_trial") === "used" ? "used" : "available";
}

export function markTrialUsed(): void {
  if (typeof document === "undefined") return;
  document.cookie = "tc_trial=used; path=/; max-age=2592000; SameSite=Lax";
}
