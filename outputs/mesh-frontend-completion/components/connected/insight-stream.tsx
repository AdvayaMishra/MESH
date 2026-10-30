"use client";
import {useEffect,useRef,useState} from "react";
import {Button} from "@/components/ui/button";
import {streamInsight} from "@/lib/connected/client";
import {useLive} from "@/lib/connected/live-state";

export function InsightStream({purpose,targetId}:{purpose:string;targetId?:string}){
 const organization=useLive(s=>s.profile?.organization_id),abort=useRef<AbortController|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[result,setResult]=useState<{summary:string;recommendations:string[];provider:string}|null>(null);
 useEffect(()=>()=>abort.current?.abort(),[]);
 return <section className="mt-4 space-y-3"><div className="flex gap-3"><Button type="button" variant="secondary" disabled={busy||!organization||(["vader","devtrack","risk"].includes(purpose)&&!targetId)} onClick={async()=>{if(!organization)return;setBusy(true);setError("");setResult(null);abort.current=new AbortController();let received=false;try{await streamInsight(purpose,targetId,organization,value=>{if(!value||typeof value!=="object")return;const item=value as Record<string,unknown>;if(typeof item.code==="string")throw new Error("Generation was interrupted. Check usage before retrying.");if(typeof item.summary==="string"&&typeof item.provider==="string"&&Array.isArray(item.recommendations)&&item.recommendations.every(v=>typeof v==="string")){received=true;setResult({summary:item.summary,recommendations:item.recommendations,provider:item.provider});}},abort.current.signal);if(!received)throw new Error("The stream ended without a complete result. Check usage before retrying.");}catch(error){setError(abort.current.signal.aborted?"Generation cancelled. Check usage before requesting another result.":error instanceof Error?error.message:"Stream unavailable");}finally{setBusy(false);abort.current=null;}}}>{busy?"Generating…":"Stream insights"}</Button>{busy&&<Button type="button" variant="secondary" onClick={()=>abort.current?.abort()}>Cancel generation</Button>}</div>{error&&<p role="alert" className="text-sm">{error}</p>}{result&&<div role="status" className="rounded-xl bg-canvas p-4 text-sm"><p>{result.summary}</p><ul className="mt-3 list-inside list-disc">{result.recommendations.map((text,i)=><li key={i}>{text}</li>)}</ul><p className="mt-3 text-xs text-ink-3">Provider: {result.provider}. Recommendations require human review.</p></div>}</section>;
}
