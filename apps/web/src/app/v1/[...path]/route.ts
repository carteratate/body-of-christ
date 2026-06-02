import { NextRequest } from "next/server";

const API_URL = process.env.API_URL;

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
  if (authorization) headers.set("authorization", authorization);
  if (contentType) headers.set("content-type", contentType);
  if (process.env.INTERNAL_API_SECRET) {
    headers.set("x-internal-secret", process.env.INTERNAL_API_SECRET);
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
export const DELETE = proxy;
