import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

// Server-side env var — not exposed to the browser
const EDITOR_ORIGIN =
  process.env.EDITOR_URL ??
  process.env.NEXT_PUBLIC_EDITOR_URL ??
  "http://localhost:8000";

/**
 * Fetch a Google identity token from the instance metadata server.
 * Returns null in local dev (metadata server unreachable).
 */
async function identityToken(): Promise<string | null> {
  try {
    const res = await fetch(
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(EDITOR_ORIGIN)}`,
      { headers: { "Metadata-Flavor": "Google" } },
    );
    if (!res.ok) return null;
    return res.text();
  } catch {
    return null;
  }
}

function buildUpstreamUrl(path: string[], search: string) {
  return `${EDITOR_ORIGIN}/${path.join("/")}${search}`;
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const token = await identityToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const upstream = await fetch(
    buildUpstreamUrl(params.path, request.nextUrl.search),
    { headers, cache: "no-store" },
  );

  const contentType = upstream.headers.get("content-type") ?? "application/json";
  const responseHeaders: Record<string, string> = { "Content-Type": contentType };

  if (contentType.includes("text/event-stream")) {
    responseHeaders["Cache-Control"] = "no-cache";
    responseHeaders["X-Accel-Buffering"] = "no";
    responseHeaders["Connection"] = "keep-alive";
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const token = await identityToken();
  const headers: Record<string, string> = {
    "Content-Type": request.headers.get("content-type") ?? "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const body = await request.arrayBuffer();

  const upstream = await fetch(buildUpstreamUrl(params.path, ""), {
    method: "POST",
    headers,
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
