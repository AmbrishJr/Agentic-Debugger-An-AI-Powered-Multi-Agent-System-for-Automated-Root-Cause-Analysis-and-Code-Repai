import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  if (
    path.some(
      (p) => p === ".." || p === "." || p.includes("/") || p.includes("\\"),
    )
  )
    return Response.json(
      { error: { message: "Invalid API path." } },
      { status: 400 },
    );
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    if (origin && new URL(origin).host !== request.headers.get("host"))
      return Response.json(
        { error: { message: "Cross-origin writes are not allowed." } },
        { status: 403 },
      );
    if (!request.headers.get("content-type")?.startsWith("application/json"))
      return Response.json(
        { error: { message: "Use application/json." } },
        { status: 415 },
      );
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (process.env.AUTORCA_API_TOKEN)
    headers["X-AutoRCA-Token"] = process.env.AUTORCA_API_TOKEN;
  try {
    let body: Uint8Array | undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader)
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > 100000) {
            await reader.cancel();
            return Response.json(
              { error: { message: "Request exceeds 100 KB." } },
              { status: 413 },
            );
          }
          chunks.push(value);
        }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.length;
      }
    }
    const upstream = await fetch(
      `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        body: body as BodyInit | undefined,
        cache: "no-store",
        signal: request.signal,
      },
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json(
      {
        error: {
          message:
            "Backend unavailable. Start FastAPI on port 8000 and try again.",
        },
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT };
