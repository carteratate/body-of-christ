import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
  delete process.env.API_URL;
  delete process.env.INTERNAL_API_SECRET;
});

describe("Vercel API proxy", () => {
  it("converts the browser user-agent to an app-owned header on the secret hop", async () => {
    process.env.API_URL = "https://api.example";
    process.env.INTERNAL_API_SECRET = "internal";
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("./[...path]/route");
    const request = new NextRequest("http://localhost/v1/product-feedback", {
      method: "POST",
      headers: {
        authorization: "Bearer token",
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 Chrome/126.0 sensitive-extra",
      },
      body: "{}",
    });

    await POST(request);

    const forwarded = fetchMock.mock.calls[0][1].headers as Headers;
    expect(forwarded.get("x-theocorpus-user-agent")).toBe("Mozilla/5.0 Chrome/126.0 sensitive-extra");
    expect(forwarded.get("x-internal-secret")).toBe("internal");
  });
});
