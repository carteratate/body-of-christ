import { NextRequest } from "next/server";

const API_URL = process.env.API_URL;

// Search is an SSE request that includes retrieval, reranking, and streamed
// explanations. Give the proxy enough lifetime for the upstream stream to finish.
export const maxDuration = 300;

async function proxy(req: NextRequest): Promise<Response> {
  if (!API_URL) {
    return new Response(JSON.stringify({ detail: "API unavailable" }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  }

  const url = new URL(req.url);
  const target = `${API_URL}${url.pathname}${url.search}`;

  // Forward only the headers the backend needs.
  // Never forward Host, Cookie, or other ambient browser headers.
  const headers = new Headers();
  const authorization = req.headers.get("authorization");
  const contentType = req.headers.get("content-type");
  const guestToken = req.headers.get("x-theocorpus-guest-token");
  if (authorization) headers.set("authorization", authorization);
  if (contentType) headers.set("content-type", contentType);
  if (guestToken) headers.set("x-theocorpus-guest-token", guestToken);
  if (process.env.INTERNAL_API_SECRET) {
    headers.set("x-internal-secret", process.env.INTERNAL_API_SECRET);
    // Vercel supplies the visitor address. Convert it to an app-owned header;
    // the API accepts it only on an authenticated proxy hop.
    const forwardedFor = req.headers.get("x-vercel-forwarded-for")
      ?? req.headers.get("x-forwarded-for");
    const clientIp = forwardedFor?.split(",", 1)[0]?.trim();
    if (clientIp) headers.set("x-theocorpus-client-ip", clientIp);
    const userAgent = req.headers.get("user-agent");
    if (userAgent) headers.set("x-theocorpus-user-agent", userAgent.slice(0, 512));
  }

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: req.method !== "GET" && req.method !== "HEAD" ? req.body : undefined,
    // Required for streaming request bodies in Node.js fetch
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ...(req.method !== "GET" && req.method !== "HEAD" ? { duplex: "half" } as any : {}),
  });

  // Pipe upstream body directly — no buffering — so SSE tokens reach the
  // browser as they arrive instead of being held until the stream closes.
  const responseHeaders = new Headers({
    "content-type": upstream.headers.get("content-type") ?? "application/json",
    "cache-control": "no-cache",
    "x-accel-buffering": "no",
  });

  // Forward Retry-After so the rate-limit modal can display an accurate countdown.
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) responseHeaders.set("retry-after", retryAfter);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
