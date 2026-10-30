import { readFile,stat } from "node:fs/promises";
import { backendBase } from "./proxy";
export const fixtureRoles=["owner","hr","senior_developer","junior_developer","security_analyst"] as const;
interface Fixture {synthetic:boolean;database_committed:boolean;expires_at:string;organization_id:string;identities:Record<string,{email:string;password:string;user_id:string}>;}
export async function dedicatedFixture():Promise<Fixture|null> {
  if(process.env.MESH_ENABLE_DEDICATED_PREVIEW!=="true" || backendBase()!=="http://127.0.0.1:8000" || !process.env.MESH_DEDICATED_PREVIEW_FILE) return null;
  try {
    const path=process.env.MESH_DEDICATED_PREVIEW_FILE;
    if((await stat(path)).size>65536)return null;
    const value=JSON.parse(await readFile(path,"utf8")) as Fixture;
    const expiry=Date.parse(value.expires_at);
    if(!value.synthetic || !value.database_committed || !Number.isFinite(expiry) || expiry<=Date.now() || expiry>Date.now()+7*86400000 || !/^[a-f0-9-]{36}$/.test(value.organization_id)) return null;
    if(Object.keys(value.identities).length!==fixtureRoles.length || !fixtureRoles.every(role=>{
      const user=value.identities[role];return user && typeof user.email==="string" && user.email.startsWith("mesh-preview-") && user.email.endsWith("@example.invalid") && typeof user.password==="string" && user.password.length>=12 && /^[a-f0-9-]{36}$/.test(user.user_id);
    }))return null;
    return value;
  }catch{return null;}
}
