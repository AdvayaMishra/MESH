"use client";
export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId: string | null) { super(message); }
}
let refreshing:Promise<boolean>|null=null;
async function refreshOnce(){
 if(!refreshing)refreshing=fetch("/api/backend/api/v1/auth/refresh",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}",credentials:"same-origin",redirect:"error",cache:"no-store"}).then(response=>response.ok).catch(()=>false).finally(()=>{refreshing=null;});
 return refreshing;
}
export async function request(path: string, method = "GET", body?: unknown, organization?: string, signal?: AbortSignal): Promise<unknown> {
  const headers: Record<string, string> = {};
  if (organization) headers["X-Organization-ID"] = organization;
  let payload: BodyInit | undefined;
  if (body instanceof File) { payload = body; headers["Content-Type"] = body.type; }
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  let response = await fetch("/api/backend" + path, { method, headers, body: payload, credentials: "same-origin", redirect:"error", cache: "no-store", signal });
  // A denied read can be retried after one shared refresh. Writes are never automatically repeated.
  if(response.status===401&&method==="GET"&&!signal?.aborted&&await refreshOnce())response=await fetch("/api/backend"+path,{method,headers,credentials:"same-origin",redirect:"error",cache:"no-store",signal});
  const data = await response.json();
  if (!response.ok) {
    const message=data?.error?.message || data?.detail || `Request failed (${response.status})`;
    const fields=Array.isArray(data?.error?.fields) ? " · Fields: "+data.error.fields.join(", ") : "";
    throw new ApiError(response.status, String(message)+fields, response.headers.get("x-request-id"));
  }
  return data;
}

export async function streamInsight(purpose:string,targetId:string|undefined,organization:string,onEvent:(value:unknown)=>void,signal:AbortSignal){
 const response=await fetch("/api/backend/api/v1/ai/stream",{method:"POST",headers:{"Content-Type":"application/json","X-Organization-ID":organization},body:JSON.stringify({purpose,target_id:targetId||null}),credentials:"same-origin",redirect:"error",cache:"no-store",signal});
 if(!response.ok||!response.body||!response.headers.get("content-type")?.startsWith("text/event-stream"))throw new Error("Insights stream unavailable. Check saved usage before retrying.");
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer="",bytes=0;
 try{while(true){const part=await reader.read();if(part.done)break;bytes+=part.value.byteLength;if(bytes>2097152)throw new Error("Stream exceeds display limit");buffer=(buffer+decoder.decode(part.value,{stream:true})).replace(/\r\n/g,"\n");let end;while((end=buffer.indexOf("\n\n"))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2);const data=block.split("\n").filter(line=>line.startsWith("data:")).map(line=>line.slice(5).trimStart()).join("\n");if(data)onEvent(JSON.parse(data));}}}finally{await reader.cancel().catch(()=>{});}
}
