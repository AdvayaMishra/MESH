/** Opt-in transport building block. No production endpoint is configured or called by the demo. */
export interface SessionContext { getAccessToken(): Promise<string | null>; getOrganizationId(): string | null }
export interface RequestOptions extends Omit<RequestInit, "headers"> { headers?: HeadersInit; signal?: AbortSignal }
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) { super(message); this.status = status; this.name = "ApiError"; }
}
export function createApiClient(baseUrl: string, session: SessionContext) {
  const base = new URL(baseUrl);
  if (!/^https?:$/.test(base.protocol)) throw new Error("API base URL must use HTTP or HTTPS");
  if (base.username || base.password || base.hash || base.search) throw new Error("API base URL must not contain credentials, query or fragment");
  return {
    async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
      // Only relative endpoint paths are accepted; bearer tokens must never be sent to a third party.
      if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) throw new Error("Expected a relative API path");
      const url = new URL(path, base);
      if (url.origin !== base.origin) throw new Error("Cross-origin API path rejected");
      const orgId = session.getOrganizationId();
      const token = await session.getAccessToken();
      if (session.getOrganizationId() !== orgId) throw new Error("Organization changed before the request");
      if (!token || !orgId) throw new Error("Authenticated session and organization are required");
      const headers = new Headers(options.headers);
      headers.set("Authorization", `Bearer ${token}`);
      headers.set("X-Organization-Id", orgId);
      headers.set("Accept", "application/json");
      const response = await fetch(url, { ...options, headers, redirect: "error", credentials: "omit", cache: "no-store" });
      if (!response.ok) throw new ApiError(response.status, `API request failed (${response.status})`);
      if (response.status === 204) return undefined as T;
      const result = await response.json() as T;
      if (session.getOrganizationId() !== orgId) throw new Error("Organization changed while awaiting the response");
      return result;
    },
  };
}
