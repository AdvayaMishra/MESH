"use client";
import {useMemo} from "react";
import {Background,Controls,ReactFlow,ReactFlowProvider,type Node,type Edge} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
type Row=Record<string,unknown>;

/** Render only returned relationships; proximity is not an inferred attack cause. */
export function ConnectedEventGraph({nodes:input,edges:links}:{nodes:unknown;edges:unknown}){
 const graph=useMemo(()=>{
  const ids=new Set<string>();
  const records=(Array.isArray(input)?input:[]).filter((value):value is Row=>!!value&&typeof value==="object"&&typeof value.id==="string"&&/^[A-Za-z0-9_-]{1,100}$/.test(value.id)&&!ids.has(value.id)&&!!ids.add(value.id)).slice(0,200);
  const visible=new Set(records.map(value=>String(value.id)));
  const nodes:Node[]=records.map((value,index)=>({id:String(value.id),position:{x:(index%3)*280,y:Math.floor(index/3)*150},data:{label:`${typeof value.category==="string"?value.category.slice(0,80):"Unknown category"}\n${typeof value.timestamp==="string"?value.timestamp:"Time not recorded"}`},style:{width:225,borderRadius:16,padding:16,whiteSpace:"pre-wrap",borderColor:"#dce3ef"}}));
  const edges:Edge[]=(Array.isArray(links)?links:[]).filter((value):value is Row=>!!value&&typeof value==="object"&&visible.has(String(value.source))&&visible.has(String(value.target))).slice(0,1000).map((value,index)=>({id:`relationship-${index}`,source:String(value.source),target:String(value.target),label:typeof value.relation==="string"?value.relation.replaceAll("_"," "):"Reported relationship",type:"smoothstep"}));
  return {nodes,edges,truncated:(Array.isArray(input)&&input.length>200)||(Array.isArray(links)&&links.length>1000)};
 },[input,links]);
 if(!graph.nodes.length)return null;
 return <div className="my-4"><div className="h-[460px] overflow-hidden rounded-2xl border border-line" aria-label="Correlated event graph"><ReactFlowProvider><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} nodesConnectable={false} minZoom={0.2} maxZoom={1.5}><Background/><Controls/></ReactFlow></ReactFlowProvider></div><p className="mt-2 text-xs text-ink-3">Relationships are reported temporal correlations and require investigation.{graph.truncated&&" Display limited to200 nodes and1000 relationships."} A text version follows.</p></div>;
}
