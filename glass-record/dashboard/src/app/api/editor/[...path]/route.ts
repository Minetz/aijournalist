import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const EDITOR_ORIGIN =
  process.env.EDITOR_URL ??
  process.env.NEXT_PUBLIC_EDITOR_URL ??
  "http://localhost:8000";

async function identityToken(audience: string): Promise<string | null> {
  try {
    const res = await fetch(
      `http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(audience)}&format=full`,
      { headers: { "Metadata-Flavor": "Google" }, cache: "no-store" },
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

async function authHeaders(): Promise<Record<string, string>> {
  const token = await identityToken(EDITOR_ORIGIN);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const upstream = await fetch(
    buildUpstreamUrl(params.path, request.nextUrl.search),
    { headers: await authHeaders(), cache: "no-store" },
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
  const body = await request.arrayBuffer();

  const upstream = await fetch(buildUpstreamUrl(params.path, ""), {
    method: "POST",
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "application/json",
      ...(await authHeaders()),
    },
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
