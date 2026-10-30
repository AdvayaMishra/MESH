"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import {useLive,displayRole,emptyDataset} from "@/lib/connected/live-state";
import {useWorkspace} from "@/stores/workspace-store";
import {useUI} from "@/stores/ui-store";
import {useTenant} from "@/stores/tenant-store";
import {Sidebar} from "@/components/layout/sidebar";
import {Topbar} from "@/components/layout/topbar";
import {CommandPalette} from "@/components/layout/command-palette";
import {RouteGuard} from "@/components/layout/route-guard";
import {Card,CardHeader,CardBody} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {LiveContent} from "@/lib/connected/content";
import {request} from "@/lib/connected/client";

export function LiveShell({children}:{children:React.ReactNode}){
 const live=useLive(),router=useRouter();const [company,setCompany]=useState("");const [organization,setOrganization]=useState("");const [sandbox,setSandbox]=useState(false);const [creating,setCreating]=useState(false),[createError,setCreateError]=useState("");
 const [ready,setReady]=useState(false);
 const [initialized,setInitialized]=useState(false);
 useEffect(()=>()=>{const d=emptyDataset();useWorkspace.setState({orgId:"",projects:[],tasks:[],findings:[],incidents:[],notifications:[],idSubmissions:[],leave:[],audit:[],complaints:[],promotions:[],sprints:[],pullRequests:[],repos:[],scanHistory:[],incidentNotes:{},incidentResponses:{},cloudRemediations:{},payrollReviews:{},payrollRun:null,prReviews:{},trustEvents:{},snapshots:{},approvalHistory:d.approvalHistory});},[]);
 useEffect(()=>{void fetch("/api/preview-info").then(r=>r.json()).then(info=>setSandbox(info.mode==="local_sandbox"));const org=localStorage.getItem("mesh-connected-organization");if(org)void useLive.getState().load(org);void Promise.resolve().then(()=>setInitialized(true));},[]);
 useEffect(()=>{
  if(!live.profile || live.loading)return;
  const d=live.data,p=live.profile;
  useWorkspace.setState({orgId:p.organization_id,projects:d.projects,tasks:d.tasks,findings:d.findings,incidents:d.incidents,notifications:d.notifications,idSubmissions:d.idSubmissions as ReturnType<typeof useWorkspace.getState>["idSubmissions"],leave:d.leaveRequests,audit:d.auditLog,approvalHistory:d.approvalHistory,complaints:d.complaints,promotions:d.promotions,sprints:d.sprints,pullRequests:d.pullRequests,repos:d.repos,scanHistory:d.scanHistory,incidentNotes:{},incidentResponses:{},cloudRemediations:{},payrollReviews:{},payrollRun:null,prReviews:{},trustEvents:{},snapshots:{}});
  useTenant.getState().setOrg(p.organization_id);useUI.setState({role:displayRole[p.role],hydrated:true});
  Promise.resolve().then(()=>setReady(true));
 },[live.profile,live.data,live.loading]);
 if(live.error&&!live.profile)return <main className="mx-auto max-w-lg p-8"><Card><CardHeader title="Your workspace could not be opened"/><CardBody><p role="alert" className="mb-4 text-sm text-ink-2">{live.error}</p><div className="flex flex-wrap gap-3"><Button asChild variant="secondary"><Link href="/mfa">Verify authenticator</Link></Button><Button onClick={()=>router.push("/login")}>Sign in again</Button></div></CardBody></Card></main>;
 if(initialized&&!live.profile&&!live.loading)return <main className="mx-auto max-w-lg p-8"><Card><CardHeader title="Welcome to MESH" subtitle="Create your organization after confirming your account."/><CardBody><form className="mb-6 space-y-3" onSubmit={async e=>{e.preventDefault();localStorage.setItem("mesh-connected-organization",organization);await live.load(organization);}}><label className="text-sm">Organization UUID<Input className="mt-2" required value={organization} onChange={e=>setOrganization(e.target.value)} pattern="[a-fA-F0-9-]{36}"/></label><Button>Connect organization</Button></form><form className="space-y-4" onSubmit={async e=>{e.preventDefault();setCreating(true);setCreateError("");try{const org=await request("/api/v1/organizations","POST",{name:company}) as {id:string};localStorage.setItem("mesh-connected-organization",org.id);await useLive.getState().load(org.id);router.push("/owner");}catch(error){setCreateError(error instanceof Error?error.message:"Could not create organization");}finally{setCreating(false);}}}><label className="text-sm">Company name<Input className="mt-2" required value={company} onChange={e=>setCompany(e.target.value)}/></label><Button disabled={creating}>Create organization</Button>{createError&&<p role="alert">{createError}</p>}</form><Button variant="ghost" className="mt-4" onClick={()=>router.push("/login")}>Back to sign in</Button></CardBody></Card></main>;
 if(!ready||!live.profile)return <main className="p-8" aria-busy="true"><div className="skeleton h-10 w-48"/><p className="mt-4 text-sm text-ink-2">Opening your workspace…</p></main>;
 return <>{sandbox&&<div role="status" className="bg-tint-amber p-3 text-center text-sm">Local sandbox · fictional identities and test data.</div>}<div className="flex min-h-dvh"><Sidebar/><div className="flex min-w-0 flex-1 flex-col"><Topbar/><main id="main" className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8">{live.warnings.length>0&&<div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-tint-amber p-3 text-sm"><span>Some services or records are unavailable. Available data is shown below.</span><Button size="sm" variant="secondary" onClick={()=>void live.refresh()}>Refresh</Button></div>}<RouteGuard><LiveContent>{children}</LiveContent></RouteGuard></main></div></div><CommandPalette/></>;
}
