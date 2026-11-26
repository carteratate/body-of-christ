import { describe, expect, it } from "vitest";
import nextConfig from "./next.config";

async function connectSrc(): Promise<string[]> {
  const rules = await nextConfig.headers!();
  const csp = rules[0].headers.find((h) => h.key === "Content-Security-Policy")!.value;
  const directive = csp.split(";").map((d) => d.trim()).find((d) => d.startsWith("connect-src"))!;
  return directive.split(/\s+/).slice(1);
}

describe("Content-Security-Policy connect-src", () => {
  it("allows PostHog's US hosts, which PostHogProvider sends to by default", async () => {
    const sources = await connectSrc();
    expect(sources).toContain("https://us.i.posthog.com");
    expect(sources).toContain("https://us-assets.i.posthog.com");
  });
});
