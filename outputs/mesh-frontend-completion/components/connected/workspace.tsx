"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { OperationPanel, operations, Result, type Operation } from "./operation-panel";
import { request } from "@/lib/connected/client";
import { usePreviewInfo } from "@/lib/connected/use-preview-info";

interface Profile { user_id:string;organization_id:string;role:string;email:string;employee_id:string|null;name?:string|null; }
type Group = "home"|"organization"|"projects"|"people"|"leave"|"payroll"|"lifecycle"|"complaints"|"documents"|"finance"|"scans"|"security"|"cloud"|"ai"|"audit"|"sessions"|"trust";
const links: {group:Group;label:string;href:string;roles?:string[]}[] = [
  {group:"home",label:"Workspace",href:"/workspace"},
  {group:"organization",label:"Organization & invitations",href:"/workspace/organization",roles:["owner","hr"]},
  {group:"projects",label:"Projects & tasks",href:"/devtrack/projects",roles:["owner","senior_developer","junior_developer"]},
  {group:"people",label:"Employee directory",href:"/people/directory",roles:["hr"]},
  {group:"leave",label:"Leave",href:"/people/leave"},
  {group:"payroll",label:"Payroll",href:"/people/payroll",roles:["hr"]},
  {group:"lifecycle",label:"Employment & lifecycle",href:"/people/lifecycle",roles:["owner","hr"]},
  {group:"complaints",label:"Complaints",href:"/workspace/complaints"},
  {group:"trust",label:"Trust Stars",href:"/workspace/trust"},
  {group:"documents",label:"Document review",href:"/people/verification",roles:["hr","owner"]},
  {group:"finance",label:"Finance & budgets",href:"/owner/finance",roles:["owner"]},
  {group:"scans",label:"Repositories & scans",href:"/devtrack/security",roles:["owner","senior_developer","security_analyst"]},
  {group:"security",label:"VADER & incidents",href:"/vader",roles:["security_analyst"]},
  {group:"cloud",label:"Cloud · deferred",href:"/vader/cloud",roles:["owner","security_analyst"]},
  {group:"ai",label:"AI insights",href:"/workspace/insights"},
  {group:"audit",label:"Audit",href:"/workspace/audit",roles:["owner","security_analyst"]},
  {group:"sessions",label:"My sessions & MFA",href:"/workspace/settings"},
];
function groupFor(path:string):Group {
  if(path.startsWith("/vader/cloud")) return "cloud";
  if(path.includes("/copilot") || path==="/workspace/insights") return "ai";
  if(path.startsWith("/vader")) return "security";
  if(path.includes("/devtrack/security") || path.includes("pull-requests")) return "scans";
  if(path.startsWith("/devtrack") || path==="/owner/projects") return "projects";
  if(path.includes("/people/payroll")) return "payroll";
  if(path.includes("/people/leave")) return "leave";
  if(path.includes("/people/lifecycle")) return "lifecycle";
  if(path.includes("/people/verification")) return "documents";
  if(path.startsWith("/people")) return "people";
  if(path.includes("/owner/finance")) return "finance";
  if(path.includes("/workspace/audit")) return "audit";
  if(path.includes("/workspace/settings")) return "sessions";
  if(path.includes("/workspace/organization")) return "organization";
  if(path.includes("/workspace/complaints")) return "complaints";
  if(path.includes("/workspace/trust")) return "trust";
  return "home";
}
function belongs(op:Operation,g:Group) {
  const p=op.path;
  switch(g) {
    case "organization":return /\/(organizations|invitations)(\/|$)/.test(p);
    case "projects":return /\/(projects|tasks|sprints|devtrack)(\/|$)/.test(p);
    case "people":return /\/employees(\/|$)|\/hr\/(departments|job-roles)/.test(p) && !p.includes("identity-documents") && !p.includes("scim-account");
    case "leave":return p.includes("/hr/leave") || p.includes("/leave-allowance/");
    case "payroll":return p.includes("/hr/payroll");
    case "lifecycle":return p.includes("/hr/lifecycle") || p.includes("/hr/employment-changes") || p.endsWith("/employment-terms");
    case "complaints":return p.includes("/hr/complaints");
    case "trust":return p.includes("/trust/");
    case "documents":return p.includes("identity-document");
    case "finance":return p.includes("/finance/") && !p.includes("/cloud-billing/");
    case "scans":return /\/(repositories|scans|findings|finding-identities)(\/|$)/.test(p) && !p.endsWith("/events");
    case "security":return p.includes("/vader/") && !p.includes("/cloud/");
    case "cloud":return p.includes("/cloud-integrations/aws/");
    case "ai":return p.includes("/ai/") && !p.endsWith("/stream");
    case "audit":return p.includes("/audit") || p.includes("/jobs");
    case "sessions":return p.includes("/users/me") || p.includes("/auth/mfa") || p==="/api/v1/auth/password";
    default:return false;
  }
}
// Navigation is advisory; every operation still uses the backend's actual fresh authorization.
function visible(op:Operation,role:string) {
  if(role==="owner" && (/\/employees|\/hr\/payroll|\/hr\/departments|\/hr\/job-roles/.test(op.path) || (op.path==="/api/v1/projects" && op.method==="POST") || (op.method==="POST" && /\/(reviews|sprints)$/.test(op.path)) || (op.path.includes("/tasks") && ["POST","PATCH"].includes(op.method)))) return false;
  if(role!=="owner" && op.path.endsWith("/organizations/current/status")) return false;
  if(role!=="owner" && op.path==="/api/v1/organizations" && op.method==="POST") return false;
  if(role==="hr" && op.path.includes("/invitations") && op.path.endsWith("/accept")) return false;
  if(role==="junior_developer" && op.path.includes("/devtrack/")) return false;
  if(op.path==="/api/v1/trust/events" && !["owner","hr"].includes(role))return false;
  return true;
}
export function ConnectedWorkspace() {
  const router=useRouter();
  const preview=usePreviewInfo();
  const pathname=usePathname(), group=groupFor(pathname);
  const [organization,setOrganization]=useState("");
  const [profile,setProfile]=useState<Profile|null>(null);
  const [error,setError]=useState("");
  const [selected,setSelected]=useState("");
  const [loading,setLoading]=useState(false);
  const generation=useRef(0);
  async function connect(org:string) {
    const run=++generation.current; setProfile(null); setError(""); setLoading(true);
    try {
      const user=await request("/api/v1/users/me","GET",undefined,org) as Profile;
      if(run===generation.current) {setProfile(user);localStorage.setItem("mesh-connected-organization",org);}
    } catch(e) {if(run===generation.current) setError(e instanceof Error ? e.message : "Could not connect");}
    finally {if(run===generation.current) setLoading(false);}
  }
  useEffect(()=>{
    const org=localStorage.getItem("mesh-connected-organization") || "";
    const counter=generation, run=++counter.current;
    if(org) request("/api/v1/users/me","GET",undefined,org).then(value=>{
      if(run===counter.current){setOrganization(org);setProfile(value as Profile);}
    }).catch(e=>{if(run===counter.current){setOrganization(org);setError(e instanceof Error?e.message:"Could not connect");}});
    return ()=>{counter.current++;};
  },[]);
  const available=operations.filter(op=>belongs(op,group) && (!profile || visible(op,profile.role)));
  const current=available.find(o=>o.method+" "+o.path===selected) || available.find(o=>o.method==="GET" && !o.path.includes("{")) || available[0];
  const nav=links.filter(l=>profile && (!l.roles || l.roles.includes(profile.role)));
  const allowed=group==="home" || !!nav.find(l=>l.group===group);
  async function logout() {
    setError("");
    try {await request("/api/v1/auth/logout","POST",{},profile?.organization_id); sessionStorage.removeItem("mesh-preview-mode"); router.push("/login");}
    catch(e) {generation.current++;setProfile(null);setError("Sign-out could not be confirmed. "+(e instanceof Error ? e.message : "Retry when the backend is available."));}
  }
  return <div className="flex min-h-dvh flex-col lg:flex-row">
    <aside className="border-b border-line bg-white p-5 lg:w-64 lg:shrink-0 lg:border-r"><Link href="/workspace"><Logo /></Link><p className="my-4 text-xs font-semibold uppercase tracking-wider text-indigo">Connected preview</p><nav className="flex flex-wrap gap-1 lg:flex-col">{nav.map(link=><Link key={link.group} href={link.href} className={`rounded-xl px-3 py-2 text-sm ${group===link.group ? "bg-tint-violet font-semibold text-indigo" : "text-ink-2 hover:bg-canvas"}`}>{link.label}</Link>)}</nav><Link className="mt-6 block text-xs text-ink-3 underline" href="/demo-login">Open separate visual demo</Link></aside>
    <div className="min-w-0 flex-1"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-6 py-4"><div><span className="font-semibold">{profile?.email || "Connect your workspace"}</span><p className="text-xs text-ink-3">{profile ? profile.role.replaceAll("_"," ") : "Real sessions · server-enforced permissions"}</p></div><div className="flex gap-2"><Button variant="secondary" onClick={async()=>{try{await request("/api/v1/auth/refresh","POST",{});if(organization) await connect(organization);}catch(e){setError(e instanceof Error?e.message:"Refresh failed");}}}>Refresh session</Button><Button variant="secondary" onClick={logout}>Sign out</Button></div></header>
    <main className="mx-auto max-w-[1480px] space-y-5 p-4 sm:p-6 lg:p-8" id="main">
      <div className="rounded-2xl border border-mint/40 bg-tint-mint p-4 text-sm">{preview.mode==="local_sandbox"?<><strong>Local sandbox · fictional identities and test data.</strong> These forms execute real MESH routes and save to an isolated local test database. Provider authentication is substituted. No hosted accounts, emails, external access changes or AWS calls are performed. This is not live Supabase acceptance.</>:<><strong>Real backend preview.</strong> Responses and saved changes come from MESH. AWS is deferred. External mail, SCIM, OCR, scanners and AI depend on their configured services.</>} Original seeded dashboards are available only in the separate visual demo.</div>
      <form className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-white p-4" onSubmit={e=>{e.preventDefault();void connect(organization);}}><label className="min-w-56 flex-1 text-sm font-medium">Organization UUID<Input aria-label="Organization UUID" className="mt-2" value={organization} onChange={e=>{generation.current++;setProfile(null);setOrganization(e.target.value);setError("");}} required /></label><Button variant="gradient" disabled={loading}>{loading?"Checking membership…":"Connect organization"}</Button><Link href="/login" className="text-sm text-indigo underline">Sign in</Link></form>
      {error && <p role="alert" className="rounded-xl bg-tint-coral p-4 text-sm">{error}</p>}
      {!profile && <Card><CardHeader title="Get started" subtitle="Sign in, then connect an organization you belong to." /><CardBody><p className="text-sm text-ink-2">If you are creating a new organization, use the form below after signing in. Save the returned ID and connect it above. A demo role selector cannot grant real permissions.</p><div className="mt-5"><OperationPanel operation={operations.find(o=>o.path==="/api/v1/organizations" && o.method==="POST")!} /></div></CardBody></Card>}
      {profile && group==="home" && <Card><CardHeader title="Your connected workspace" subtitle="Use the navigation to inspect records or submit a supported workflow." /><CardBody><Result value={profile} /><p className="mt-4 text-sm text-ink-2">Each feature offers backend-backed forms and results using the supplied frontend&apos;s components. This temporary preview does not claim every original demo widget is live. Permission denials and unavailable services are shown as returned.</p></CardBody></Card>}
      {profile && !allowed && <Card><CardHeader title="This view is not available to your role" /><CardBody><p className="text-sm">Choose a permitted section from the navigation. Owner access does not include confidential HR records or raw analyst investigations.</p></CardBody></Card>}
      {profile && allowed && group!=="home" && <section className="space-y-4"><h1 className="font-display text-2xl font-bold">{links.find(l=>l.group===group)?.label}</h1>
        {group==="cloud" && <p className="rounded-xl bg-tint-amber p-4 text-sm">Live AWS is deferred. These local status checks do not contact AWS. Billing samples, if explicitly requested, are labelled synthetic and never enter actual finance records.</p>}
        {group==="ai" && <p className="text-sm text-ink-2">Choose a supported scoped insight. Generation can consume provider usage. Each click submits once; failures are not automatically retried.</p>}
        {available.length>0 && <><label className="block text-sm font-medium">Workflow<Select aria-label="Workflow" className="mt-2" value={current?.method+" "+current?.path} onChange={e=>setSelected(e.target.value)}>{available.map(o=><option key={o.method+o.path} value={o.method+" "+o.path}>{o.title} · {o.method}</option>)}</Select></label>{current && <OperationPanel key={profile.organization_id+profile.user_id+current.method+current.path} operation={current} organization={profile.organization_id} onSession={()=>void connect(organization)} />}</>}
      </section>}
    </main></div></div>;
}
