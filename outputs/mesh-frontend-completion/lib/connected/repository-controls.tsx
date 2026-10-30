"use client";
import {useState} from "react";
import {Card,CardHeader,CardBody} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Field,Input,Select} from "@/components/ui/input";
import {useLive} from "./live-state";
import {request} from "./client";
import {ErrorMessage,rows} from "./hr";
import {useResource,RecordTable} from "./security";
type Row=Record<string,unknown>;
export function LiveRepositorySetup(){
 const live=useLive(),[created,setCreated]=useState<Row|null>(null),[finding,setFinding]=useState(""),[selected,setSelected]=useState("");
 const history=useResource(selected?`/api/v1/findings/${selected}/history?limit=100`:"");
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
 return <div className="space-y-6">{live.profile?.role==="owner"&&<Card><CardHeader title="Connect a repository" subtitle="Requires an authorized GitHub App installation and an approved project. The backend validates access."/><CardBody>
 <form className="grid gap-4 sm:grid-cols-2" onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);setBusy(true);setError("");try{setCreated(await request("/api/v1/repositories","POST",{full_name:data.get("name"),installation_id:Number(data.get("installation")),project_id:data.get("project")},live.profile?.organization_id) as Row);}catch(e){setError(e instanceof Error?e.message:"Repository could not be connected");}finally{setBusy(false);}}}>
 <Field label="GitHub repository (owner/name)" htmlFor="repo-full-name"><Input id="repo-full-name" name="name" pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+" required/></Field><Field label="GitHub App installation number" htmlFor="repo-installation"><Input id="repo-installation" name="installation" type="number" min="1" step="1" required/></Field><Field label="Approved project" htmlFor="repo-project"><Select id="repo-project" name="project" required defaultValue=""><option value="" disabled>Choose a project</option>{live.data.projects.filter(p=>p.status==="Active").map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field><div><Button disabled={busy}>Connect repository</Button></div></form>
 {created&&<div role="status" className="mt-4 text-sm"><p>{String(created.full_name)} connected.</p><p className="break-all">Repository reference: {String(created.id)}</p><p>Use this reference in the scan panel below.</p></div>}
 </CardBody></Card>}{live.profile?.role!=="owner"&&<Card><CardHeader title="Review a finding" subtitle="Disposition updates are authorized by the backend and retained in finding history."/><CardBody>
 <form className="grid gap-4 sm:grid-cols-2" onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);setBusy(true);setError("");setMessage("");try{await request(`/api/v1/findings/${finding}`,"PATCH",{status:data.get("status")},live.profile?.organization_id);setSelected(finding);history.refresh();setMessage("Finding disposition saved.");}catch(e){setError(e instanceof Error?e.message:"Finding update failed");}finally{setBusy(false);}}}>
 <Field label="Finding reference" htmlFor="finding-reference"><Input id="finding-reference" value={finding} onChange={e=>setFinding(e.target.value)} required pattern="[a-fA-F0-9-]{36}"/></Field><Field label="Disposition" htmlFor="finding-status"><Select id="finding-status" name="status">{["triaged","investigating","confirmed","false_positive","resolved","accepted_risk","open"].map(s=><option key={s} value={s}>{s.replaceAll("_"," ")}</option>)}</Select></Field><div className="flex gap-3"><Button disabled={busy}>Save disposition</Button><Button type="button" variant="secondary" disabled={!finding} onClick={()=>{setSelected(finding);history.refresh();}}>Load history</Button></div></form>
 <ErrorMessage error={error||history.error}/>{message&&<p role="status" className="mt-3 text-sm">{message}</p>}{selected&&<RecordTable data={rows(history.data)} columns={[["created_at","Changed"],["status","Disposition"],["actor_id","Reviewer reference"]]}/>}
 </CardBody></Card>}</div>;
}
