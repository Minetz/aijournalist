import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const EDITOR_ORIGIN =
  process.env.EDITOR_URL ??
  process.env.NEXT_PUBLIC_EDITOR_URL ??
  "http://localhost:8000";

function buildUpstreamUrl(path: string[], search: string) {
  return `${EDITOR_ORIGIN}/${path.join("/")}${search}`;
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const upstream = await fetch(
    buildUpstreamUrl(params.path, request.nextUrl.search),
    { cache: "no-store" },
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
