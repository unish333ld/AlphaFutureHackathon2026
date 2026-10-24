import { ApiError } from "./errors";

let csrf: string | null = null;
let csrfRequest: Promise<string> | null = null;
export function setCsrf(value: string | null) {
  csrf = value;
}
export async function csrfToken(force = false): Promise<string> {
  if (csrf && !force) return csrf;
  csrfRequest ??= request<{ csrf_token: string }>("session/csrf/")
    .then((result) => {
      csrf = result.csrf_token;
      return result.csrf_token;
    })
    .finally(() => {
      csrfRequest = null;
    });
  return csrfRequest;
}

export async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    signal?: AbortSignal;
    idempotencyKey?: string;
  } = {},
): Promise<T> {
  if (!/^[a-z0-9/\-?=&_%+]+$/i.test(path)) throw new Error("Invalid API path");
  // A queued detail read may be cancelled before its concurrency slot is free.
  // Do not invoke WebKit fetch with a pre-aborted signal (it emits spurious CORS errors).
  options.signal?.throwIfAborted();
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (method !== "GET") headers.set("X-CSRFToken", await csrfToken());
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  if (options.idempotencyKey)
    headers.set("Idempotency-Key", options.idempotencyKey);
  let response: Response;
  try {
    options.signal?.throwIfAborted();
    response = await fetch(`/api/v1/${path}`, {
      method,
      credentials: "include",
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(20000)])
        : AbortSignal.timeout(20000),
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(0, null);
  }
  const raw =
    response.status === 204 ? null : await response.text().catch(() => null);
  let data: unknown = null;
  try {
    data = raw ? (JSON.parse(raw) as unknown) : null;
  } catch {
    /* Do not display HTML/tracebacks. */
  }
  if (!response.ok) {
    if (response.status === 403 && !["me/", "session/login/"].includes(path)) {
      setCsrf(null);
      window.dispatchEvent(new Event("credit:check-session"));
    }
    const retryHeader = response.headers.get("Retry-After") ?? "0";
    const retryAfter = /^\d+$/.test(retryHeader)
      ? Number(retryHeader)
      : Math.max(0, Math.ceil((Date.parse(retryHeader) - Date.now()) / 1000));
    throw new ApiError(
      response.status,
      data,
      Number.isFinite(retryAfter) ? retryAfter : 0,
    );
  }
  if (response.status !== 204 && data === null) throw new ApiError(0, null);
  return data as T;
}
