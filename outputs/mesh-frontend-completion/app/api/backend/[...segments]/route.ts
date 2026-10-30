import { NextRequest } from "next/server";
import { proxy } from "@/lib/connected/proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ segments: string[] }> };
async function handle(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).segments);
}
export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
