export function classifySearchErrorCode(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("rate limit") || lower.includes("429")) return "rate_limit";
  if (lower.includes("unauthorized") || lower.includes("401") || lower.includes("403")) {
    return "auth_error";
  }
  if (lower.includes("network") || lower.includes("fetch")) return "network_error";
  return "server_error";
}
