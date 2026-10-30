import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { NextRequest, NextResponse } from "next/server";
import { bounded, sameOrigin } from "@/lib/connected/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Local operator acceptance only: no user creation, mail or successful session. */
export async function POST(request: NextRequest) {
  const reply = (status: number, message: string) => NextResponse.json({message}, {status, headers:{"Cache-Control":"no-store"}});
  if (!sameOrigin(request)) return reply(403, "Same-origin loopback request required");
  if (process.env.MESH_ENABLE_CAPTCHA_CHECK !== "true") return reply(404, "Check unavailable");
  const url = process.env.MESH_CAPTCHA_SUPABASE_URL;
  const key = process.env.MESH_CAPTCHA_SUPABASE_PUBLIC_KEY;
  if (url !== "https://znnyaieilgekmzebewge.supabase.co" || !key) return reply(503, "Check is not configured");
  let token: unknown;
  try { token = JSON.parse(new TextDecoder().decode(await bounded(request.body, 8192))).captcha_token; }
  catch { return reply(400, "Complete the challenge first"); }
  if (typeof token !== "string" || !token || token.length > 4096) return reply(400, "Complete the challenge first");
  const email = `mesh-captcha-check-${randomUUID()}@example.invalid`;
  const password = randomUUID()+"A1!";
  async function probe(captcha: string) {
    const response = await fetch(url+"/auth/v1/token?grant_type=password", {method:"POST", headers:{apikey:key!,"Content-Type":"application/json"},body:JSON.stringify({email,password,gotrue_meta_security:{captcha_token:captcha}}),cache:"no-store",redirect:"error",signal:AbortSignal.timeout(15000)});
    const data = JSON.parse(new TextDecoder().decode(await bounded(response.body, 65536)));
    return {status:response.status,code:data.error_code ?? data.code};
  }
  try {
    const first = await probe(token);
    const accepted = first.status === 400 && first.code === "invalid_credentials";
    const second = accepted ? await probe(token) : null;
    const replayRejected = second?.status === 400 && second.code === "captcha_failed";
    const report = {checked_at_utc:new Date().toISOString(),real_cloudflare_token_accepted:accepted,reused_token_rejected:replayRejected,passed:accepted&&replayRejected,accounts_created:false,emails_sent:false,production_clearance:false};
    await mkdir("verification",{recursive:true});
    await writeFile("verification/turnstile-live-challenge-results.json",JSON.stringify(report,null,2)+"\n");
    return reply(report.passed ? 200 : 400, report.passed ? "Verified: Supabase accepted the real CAPTCHA and rejected token reuse. No account was created." : "The live check did not pass. Complete a fresh challenge and try again; check the configured keys and allowed hostnames.");
  } catch { return reply(503, "Provider check unavailable. Complete a fresh challenge before retrying."); }
}
