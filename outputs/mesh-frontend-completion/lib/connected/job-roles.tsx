"use client";
import {useState} from "react";
import {Card,CardHeader,CardBody} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Field,Input} from "@/components/ui/input";
import {useLive} from "./live-state";
import {request} from "./client";
import {useResource,RecordTable} from "./security";
import {ErrorMessage} from "./hr";

export function LiveJobRoles(){
 const live=useLive(),resource=useResource(live.profile?.role==="hr"?"/api/v1/hr/job-roles?limit=100":""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 if(live.profile?.role!=="hr")return null;
 return <Card><CardHeader title="Job roles and compensation bands" subtitle="Versioned role definitions are separate from application access permissions."/><CardBody><RecordTable data={Array.isArray(resource.data)?resource.data:[]} columns={[["title","Job title"],["grade","Grade"],["version","Version"],["currency","Currency"],["minimum_base","Minimum base"],["maximum_base","Maximum base"]]}/><form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);setBusy(true);setError("");try{await request("/api/v1/hr/job-roles","POST",{...Object.fromEntries(data),version:Number(data.get("version"))},live.profile?.organization_id);resource.refresh();await live.refresh();form.reset();}catch(error){setError(error instanceof Error?error.message:"Job role could not be saved");}finally{setBusy(false);}}}><Field label="Job title"><Input name="title" required maxLength={100}/></Field><Field label="Grade"><Input name="grade" required maxLength={40}/></Field><Field label="Job role version"><Input name="version" type="number" min={1} required/></Field><Field label="Compensation currency"><Input name="currency" pattern="[A-Z]{3}" defaultValue="USD" required/></Field><Field label="Minimum base"><Input name="minimum_base" type="number" min={0} step="0.01" required/></Field><Field label="Maximum base"><Input name="maximum_base" type="number" min={0} step="0.01" required/></Field><Button disabled={busy}>Save job role</Button></form><ErrorMessage error={error||resource.error}/></CardBody></Card>;
}

export function LiveAIUsage(){
 const requests=useResource("/api/v1/ai/requests?limit=100");
 return <Card><CardHeader title="AI request accounting" subtitle="Saved request states and provisional accounting; these records are not verified provider invoices."/><CardBody><ErrorMessage error={requests.error}/><RecordTable data={Array.isArray(requests.data)?requests.data:[]} columns={[["purpose","Purpose"],["status","Status"],["provider","Provider"],["model","Model"],["created_at","Requested"],["currency","Currency"],["estimated_cost","Estimated cost"]]}/></CardBody></Card>;
}
