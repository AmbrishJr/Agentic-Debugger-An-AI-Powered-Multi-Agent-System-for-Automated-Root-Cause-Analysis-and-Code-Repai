export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let csrf = "";
  if (
    init?.method &&
    !["GET", "HEAD"].includes(init.method) &&
    path !== "/auth/login"
  ) {
    const session = await fetch("/api/auth/me", { cache: "no-store" });
    csrf = (await session.json()).csrf_token || "";
  }
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...init?.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/me")
    window.dispatchEvent(new Event("autorca-session-expired"));
  if (!response.ok)
    throw new Error(
      data.error?.message || "The server could not complete the request.",
    );
  return data;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
