import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import ts from "typescript";
const source=await readFile(new URL("../lib/connected/client.ts",import.meta.url),"utf8");
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {request}=await import("data:text/javascript;base64,"+Buffer.from(js).toString("base64"));

test("expired reads refresh once and retry without exposing session tokens",async()=>{
 const original=globalThis.fetch,calls=[];let reads=0;
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json(url.endsWith("/refresh")?{session_created:true}:++reads===1?{error:{message:"Expired"}}:{ok:true},{status:url.endsWith("/refresh")?200:reads===1?401:200});};
 try{assert.deepEqual(await request("/api/v1/users/me"),{ok:true});assert.equal(calls.length,3);assert.equal(calls[1].url,"/api/backend/api/v1/auth/refresh");assert.equal(calls[1].options.redirect,"error");}finally{globalThis.fetch=original;}
});
test("failed writes are never automatically refreshed or repeated",async()=>{
 const original=globalThis.fetch,calls=[];
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return Response.json({error:{message:"Expired"}},{status:401});};
 try{await assert.rejects(request("/api/v1/projects","POST",{name:"Synthetic request"}),error=>error.status===401);assert.equal(calls.length,1);assert.equal(calls[0].options.redirect,"error");}finally{globalThis.fetch=original;}
});
test("concurrent denied reads share one refresh",async()=>{
 const original=globalThis.fetch,seen=new Set();let refreshes=0;
 globalThis.fetch=async(url)=>{if(url.endsWith("/refresh")){refreshes++;await new Promise(resolve=>setTimeout(resolve,10));return Response.json({session_created:true});}if(!seen.has(url)){seen.add(url);return Response.json({error:{message:"Expired"}},{status:401});}return Response.json({ok:true});};
 try{await Promise.all([request("/api/v1/first"),request("/api/v1/second")]);assert.equal(refreshes,1);}finally{globalThis.fetch=original;}
});
