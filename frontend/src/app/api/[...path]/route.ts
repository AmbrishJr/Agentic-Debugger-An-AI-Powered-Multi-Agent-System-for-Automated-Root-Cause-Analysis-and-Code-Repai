import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 300;
async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  if (process.env.VERCEL === "1" && (!process.env.BACKEND_URL || !process.env.AUTORCA_API_TOKEN))
    return Response.json({ error: { message: "The workspace backend is not configured." } }, { status: 503 });
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
  for (const name of ["cookie", "x-csrf-token"]) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  if (process.env.AUTORCA_API_TOKEN)
    headers["X-AutoRCA-Token"] = process.env.AUTORCA_API_TOKEN;
  if (process.env.AUTORCA_BACKEND_BYPASS_SECRET)
    headers["x-vercel-protection-bypass"] = process.env.AUTORCA_BACKEND_BYPASS_SECRET;
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
        redirect: "error",
        signal: request.signal,
      },
    );
    const responseHeaders = new Headers({
      "Content-Type":
        upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    });
    for (const cookie of upstream.headers.getSetCookie())
      responseHeaders.append("Set-Cookie", cookie);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        error: {
          message:
            "Backend unavailable. Check the workspace service configuration and try again.",
        },
      },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT };
