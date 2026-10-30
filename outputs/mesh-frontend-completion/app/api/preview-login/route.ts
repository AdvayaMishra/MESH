import { NextRequest,NextResponse } from "next/server";
import { bounded,proxy,sameOrigin } from "@/lib/connected/proxy";
import { dedicatedFixture,fixtureRoles } from "@/lib/connected/dedicated";
export const runtime="nodejs";
export const dynamic="force-dynamic";
export async function POST(request:NextRequest) {
  const error=(status:number,message:string)=>NextResponse.json({error:{message}},{status,headers:{"Cache-Control":"no-store"}});
  if(!sameOrigin(request))return error(403,"Same-origin loopback request required");
  const fixture=await dedicatedFixture();if(!fixture)return error(503,"Dedicated local preview accounts are not enabled or have expired");
  let role:string;let captcha:string;
  try {const body=JSON.parse(new TextDecoder().decode(await bounded(request.body,8192)));role=body.role;captcha=body.captcha_token;}catch{return error(400,"Choose a dedicated preview role");}
  if(!fixtureRoles.includes(role as typeof fixtureRoles[number]))return error(400,"Choose a dedicated preview role");
  if(typeof captcha!=="string"||!captcha||captcha.length>4096)return error(400,"Complete bot verification first");
  const user=fixture.identities[role];
  // Passwords remain server-side. This is a real backend/Supabase sign-in for
  // one of the exact, human-approved synthetic identities, not a role override.
  const login=new NextRequest(request.nextUrl.protocol+"//"+request.headers.get("host")+"/api/backend/api/v1/auth/login",{method:"POST",headers:{"Origin":request.headers.get("origin")!,"Host":request.headers.get("host")!,"Content-Type":"application/json"},body:JSON.stringify({email:user.email,password:user.password,captcha_token:captcha})});
  return proxy(login,["api","v1","auth","login"]);
}
