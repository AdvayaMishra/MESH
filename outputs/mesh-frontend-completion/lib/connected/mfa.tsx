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
export function LiveMfa(){
 const live=useLive(),factors=useResource("/api/v1/auth/mfa/factors",false);
 const [enrolled,setEnrolled]=useState<Row|null>(null),[factor,setFactor]=useState(""),[challenge,setChallenge]=useState(""),[code,setCode]=useState("");
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
 async function action(path:string,method:string,body?:Row){setBusy(true);setError("");setMessage("");try{return await request(path,method,body,live.profile?.organization_id) as Row;}catch(e){setError(e instanceof Error?e.message:"Authenticator operation failed");return null;}finally{setBusy(false);}}
 const secret=(enrolled?.totp as Row|undefined)?.secret;
 return <Card><CardHeader title="Two-factor authentication" subtitle="Authenticator enrollment and verification are handled by Supabase. Keep setup secrets private."/><CardBody>
 <ErrorMessage error={factors.error||error}/><RecordTable data={rows((factors.data as Row|null)?.factors)} columns={[["friendly_name","Authenticator"],["status","Status"]]}/>
 <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={async e=>{e.preventDefault();const data=new FormData(e.currentTarget);const r=await action("/api/v1/auth/mfa/enroll","POST",{friendly_name:data.get("name")});if(r){setEnrolled(r);setFactor(String(r.id));setChallenge("");factors.refresh();}}}>
 <Field label="Authenticator name" htmlFor="mfa-name"><Input id="mfa-name" name="name" required maxLength={100} defaultValue="MESH authenticator"/></Field><Button disabled={busy}>Add authenticator</Button></form>
 {secret!=null&&<div className="mt-4 rounded-xl bg-canvas p-4 text-sm"><p>Add this setup key manually in your authenticator app:</p><code className="break-all">{String(secret)}</code><p className="mt-2 text-xs text-ink-3">This key is shown only in temporary page memory. Verification clears it.</p></div>}
 <form className="mt-5 flex flex-wrap items-end gap-3" onSubmit={async e=>{e.preventDefault();const r=await action(`/api/v1/auth/mfa/factors/${factor}/challenge`,"POST",{});if(r)setChallenge(String(r.id));}}>
 <Field label="Authenticator to verify" htmlFor="mfa-factor"><Select id="mfa-factor" value={factor} onChange={e=>{setFactor(e.target.value);setChallenge("");}} required><option value="">Choose an authenticator</option>{rows((factors.data as Row|null)?.factors).map(f=><option key={String(f.id)} value={String(f.id)}>{String(f.friendly_name||"Authenticator")} · {String(f.status)}</option>)}{enrolled&&!rows((factors.data as Row|null)?.factors).some(f=>f.id===enrolled.id)&&<option value={String(enrolled.id)}>{String(enrolled.friendly_name)}</option>}</Select></Field><Button disabled={busy||!factor} variant="secondary">Start verification</Button></form>
 {challenge&&<form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={async e=>{e.preventDefault();const r=await action(`/api/v1/auth/mfa/factors/${factor}/verify`,"POST",{challenge_id:challenge,code});setCode("");if(r){setChallenge("");setEnrolled(null);setMessage("Authenticator verified and session updated.");factors.refresh();}}}>
 <Field label="Six-digit authenticator code" htmlFor="mfa-code"><Input id="mfa-code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" value={code} onChange={e=>setCode(e.target.value)} required/></Field><Button disabled={busy}>Verify authenticator</Button></form>}
 <Button className="mt-5" variant="secondary" disabled={busy||!factor} onClick={async()=>{if(!window.confirm("Remove this authenticator? Your provider may require a recently verified session."))return;setBusy(true);setError("");try{await request(`/api/v1/auth/mfa/factors/${factor}`,"DELETE",undefined,live.profile?.organization_id);setEnrolled(null);setFactor("");setChallenge("");setMessage("Authenticator removed.");factors.refresh();}catch(e){setError(e instanceof Error?e.message:"Authenticator could not be removed");}finally{setBusy(false);}}}>Remove selected authenticator</Button>
 {message&&<p role="status" className="mt-4 text-sm">{message}</p>}
 </CardBody></Card>;
}
