import { NextResponse } from "next/server";
import { backendBase } from "@/lib/connected/proxy";
import { dedicatedFixture } from "@/lib/connected/dedicated";
export const dynamic="force-dynamic";
export async function GET() {
  // This flag can only describe the dedicated local identity/database fixture.
  const sandbox=process.env.MESH_LOCAL_SANDBOX==="true" && backendBase()==="http://127.0.0.1:8011";
  const dedicated=await dedicatedFixture();
  return NextResponse.json({mode:sandbox?"local_sandbox":"connected",dedicated_accounts_available:!!dedicated,organization_id:sandbox?"11111111-1111-4111-8111-111111111111":dedicated?.organization_id || null},{headers:{"Cache-Control":"no-store"}});
}
