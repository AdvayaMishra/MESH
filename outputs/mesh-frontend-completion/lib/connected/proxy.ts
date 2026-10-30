import {boundedEventStream} from "./bounded-stream";
import { NextRequest, NextResponse } from "next/server";
import contract from "./contract.json";

const CHUNK = 3000;
const MAX_CHUNKS = 6;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function cookieRoot(): string {
  return process.env.MESH_LOCAL_SANDBOX === "true" && backendBase() === "http://127.0.0.1:8011" ? "mesh_sandbox" : "mesh";
}
const mutates = (method: string) => !["GET", "HEAD"].includes(method);
export function sameOrigin(request: NextRequest): boolean {
  // NextURL normalizes 127.0.0.1 to localhost. Compare the browser's exact Host
  // instead, while restricting this intentionally local preview to loopback.
  const host=request.headers.get("host") || "";
  return /^(localhost|127\.0\.0\.1|\[::1\])(:[0-9]{1,5})?$/.test(host) && request.headers.get("origin") === request.nextUrl.protocol+"//"+host;
}
const options = (request: NextRequest) => ({ httpOnly: true, sameSite: "strict" as const, secure: request.nextUrl.protocol === "https:", path: "/" });
export function readToken(request: NextRequest, kind: "access" | "refresh"): string {
  const count = Number(request.cookies.get(`${cookieRoot()}_${kind}_count`)?.value ?? 0);
  if (!Number.isInteger(count) || count < 1 || count > MAX_CHUNKS) return "";
  const chunks = Array.from({ length: count }, (_, i) => request.cookies.get(`${cookieRoot()}_${kind}_${i}`)?.value);
  return chunks.every(Boolean) ? chunks.join("") : "";
}
function clear(response: NextResponse, request: NextRequest) {
  for (const kind of ["access", "refresh"]) {
    for (const suffix of ["count", ...Array.from({ length: MAX_CHUNKS }, (_, i) => String(i))])
      response.cookies.set(`${cookieRoot()}_${kind}_${suffix}`, "", { ...options(request), maxAge: 0 });
  }
}
function save(response: NextResponse, request: NextRequest, values: Record<string, unknown>) {
  const access = values.access_token, refresh = values.refresh_token;
  if (typeof access !== "string" || typeof refresh !== "string" || !access || !refresh || access.length > 16384 || refresh.length > 8192) throw new Error("Invalid session");
  clear(response, request);
  for (const [kind, value] of [["access", access], ["refresh", refresh]]) {
    const count = Math.ceil(value.length / CHUNK);
    response.cookies.set(`${cookieRoot()}_${kind}_count`, String(count), options(request));
    for (let i = 0; i < count; i++) response.cookies.set(`${cookieRoot()}_${kind}_${i}`, value.slice(i * CHUNK, (i + 1) * CHUNK), options(request));
  }
}
function fail(status: number, message: string) {
  return NextResponse.json({ error: { message } }, { status, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } });
}
export async function bounded(body: ReadableStream<Uint8Array> | null, limit: number): Promise<Uint8Array> {
  if (!body) return new Uint8Array();
  const reader = body.getReader();
  const chunks: Uint8Array[] = []; let length = 0;
  try {
    while (true) {
      const item = await reader.read();
      if (item.done) break;
      length += item.value.length;
      if (length > limit) throw new Error("Body limit");
      chunks.push(item.value);
    }
  } catch (error) { await reader.cancel(); throw error; }
  const joined = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  return joined;
}
export function backendBase(): string {
  const url = new URL(process.env.MESH_BACKEND_URL || "http://127.0.0.1:8000");
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/" || !["http:", "https:"].includes(url.protocol)) throw new Error("Invalid backend URL");
  if (url.protocol === "http:" && !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) throw new Error("Remote backend requires HTTPS");
  return url.origin;
}
export async function proxy(request: NextRequest, segments: string[]) {
  if (segments.some(s => !/^[A-Za-z0-9_-]+$/.test(s))) return fail(400, "Invalid API path");
  const path = "/" + segments.join("/");
  const operation = contract.operations.find(op => op.method === request.method && new RegExp("^" + op.path.replace(/\{[^}]+\}/g, "[A-Za-z0-9_-]+") + "$").test(path));
  if (!operation) return fail(404, "Operation is not in the reviewed backend contract");
  if (mutates(request.method) && !sameOrigin(request)) return fail(403, "Same-origin loopback request required");
  const streaming=path === "/api/v1/ai/stream" || /\/scans\/[^/]+\/events$/.test(path);
  const tenant = request.headers.get("x-organization-id") || "";
  if (tenant && !uuid.test(tenant)) return fail(400, "Select a valid organization UUID");
  const access = readToken(request, "access");
  if (operation.authenticated && !access) return fail(401, "Sign in to the connected preview");
  const headers = new Headers({ Accept: "application/json", "Accept-Encoding": "identity" });
  if (access) headers.set("Authorization", "Bearer " + access);
  if (tenant) headers.set("X-Organization-ID", tenant);
  let payload: BodyInit | undefined;
  if (mutates(request.method)) {
    const type = request.headers.get("content-type")?.split(";")[0] || "";
    const image = /\/employees\/[^/]+\/identity-documents$/.test(path) && request.method === "POST";
    if (image && !["image/png", "image/jpeg"].includes(type)) return fail(415, "Upload a JPEG or PNG image");
    if (!image && request.body && type !== "application/json") return fail(415, "JSON request required");
    let bytes: Uint8Array;
    try { bytes = await bounded(request.body, image ? 2097152 : 262144); } catch { return fail(413, "Request exceeds the preview upload limit"); }
    if (path === "/api/v1/auth/refresh") {
      const refresh = readToken(request, "refresh");
      if (!refresh) return fail(401, "Sign in again");
      payload = JSON.stringify({ refresh_token: refresh });
    } else payload = bytes.length ? new Blob([bytes as BlobPart]) : undefined;
    if (payload) headers.set("Content-Type", image ? type : "application/json");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  let streamOpen=false;
  const disconnected=()=>controller.abort();
  request.signal.addEventListener("abort",disconnected,{once:true});
  const cleanup=()=>{clearTimeout(timer);request.signal.removeEventListener("abort",disconnected);};
  try {
    const upstream = await fetch(backendBase() + path + request.nextUrl.search, { method: request.method, headers, body: payload, cache: "no-store", redirect: "manual", signal: controller.signal });
    if (upstream.status >= 300 && upstream.status < 400) return fail(502, "Backend redirects are not accepted");
    if(streaming&&upstream.ok){
      if(!upstream.headers.get("content-type")?.startsWith("text/event-stream")||!upstream.body)return fail(502,"Backend returned an unsupported stream");
      streamOpen=true;
      return new Response(boundedEventStream(upstream.body,controller,cleanup),{status:upstream.status,headers:{"Content-Type":"text/event-stream","Cache-Control":"no-store","X-Content-Type-Options":"nosniff","X-Accel-Buffering":"no"}});
    }
    const bytes = await bounded(upstream.body, 2097152);
    let data: Record<string, unknown> | unknown[] | null;
    try { data = bytes.length ? JSON.parse(new TextDecoder().decode(bytes)) : null; } catch { return fail(502, "Backend returned an unsupported response"); }
    const session = path.startsWith("/api/v1/auth/") && upstream.ok && data && !Array.isArray(data) && "access_token" in data;
    const result = NextResponse.json(session ? { session_created: true, expires_in: (data as Record<string, unknown>).expires_in } : data, { status: upstream.status === 204 ? 200 : upstream.status });
    result.headers.set("Cache-Control", "no-store");
    result.headers.set("X-Content-Type-Options", "nosniff");
    const requestId = upstream.headers.get("x-request-id");
    if (requestId) result.headers.set("X-Request-ID", requestId);
    if (session) save(result, request, data as Record<string, unknown>);
    if (path === "/api/v1/auth/logout" || (path === "/api/v1/auth/refresh" && [400,401,403].includes(upstream.status))) clear(result, request);
    return result;
  } catch {
    const response = fail(503, "Backend unavailable or response incomplete. A submitted change may have completed; check its status before retrying.");
    if (path === "/api/v1/auth/logout") clear(response, request);
    return response;
  }
  finally { if(!streamOpen)cleanup(); }
}
