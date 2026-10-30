"use client";
import {create} from "zustand";
import {makeDataset,type RawDataset,type Dataset} from "@/lib/api/dataset";
import type {Role,Employee,Project,Task,Incident} from "@/lib/types";
import {request,ApiError} from "./client";

export interface LiveProfile {user_id:string;organization_id:string;role:string;email:string;employee_id:string|null;name:string|null;owner_name:string|null;}
type Row=Record<string,unknown>;
const row=(v:unknown):Row=>v && typeof v==="object"&&!Array.isArray(v)?v as Row:{};
const rows=(v:unknown):Row[]=>Array.isArray(v)?v.map(row):[];
const str=(v:unknown,fallback="")=>typeof v==="string"?v:fallback;
const number=(v:unknown,fallback=0)=>v!==null&&v!==undefined&&Number.isFinite(Number(v))?Number(v):fallback;
export const displayRole:Record<string,Role>={owner:"owner",hr:"hr",senior_developer:"senior-dev",junior_developer:"junior-dev",security_analyst:"security-analyst"};
export const backendRole:Record<Role,string>={owner:"owner",hr:"hr","senior-dev":"senior_developer","junior-dev":"junior_developer","security-analyst":"security_analyst"};
export const isLive=()=>typeof window!=="undefined"&&sessionStorage.getItem("mesh-preview-mode")!=="demo";
export async function logoutLive(){try{await request("/api/v1/auth/logout","POST",{},useLive.getState().profile?.organization_id);}finally{useLive.getState().reset();localStorage.removeItem("mesh-connected-organization");}}
export function emptyDataset():Dataset {
  return makeDataset({id:"",simulatedLabel:"Connected",org:{name:"Your organization",domain:"",plan:"Connected workspace",region:""},roleUsers:{owner:"",hr:"","senior-dev":"","junior-dev":"","security-analyst":""},approvalHistory:{},
    monthlyCost:[],providerSplit:[],utilization:[],orgKpis:{totalEmployees:0,employeeDelta:Number.NaN,activeProjects:0,projectDelta:Number.NaN,monthlyCloudSpend:Number.NaN,spendDelta:Number.NaN,pendingApprovals:0,openIncidents:0,incidentDelta:Number.NaN,securityPosture:Number.NaN,postureDelta:Number.NaN},kpiSparks:{employees:[],projects:[],spend:[],approvals:[],incidents:[],posture:[]},whatIfPrompts:[],whatIfScenarios:{},departmentStats:[],projects:[],tasks:[],sprints:[],pullRequests:[],repos:[],findings:[],vulnTrend:[],scanHistory:[],dependencyRisk:[],incidents:[],attackChain:[],riskComponents:[],riskTrend:[],riskChangeLog:[],loginActivity:[],apiUsage:[],deviceTimeline:[],downloadAnomalies:[],employeeRiskDistribution:[],cloudResources:[],cloudPosture:{score:Number.NaN,byProvider:[]},payrollSummary:{month:"No payroll summary available",gross:Number.NaN,net:Number.NaN,taxes:Number.NaN,benefits:Number.NaN,headcount:0,trend:[],byDept:[],discrepancies:[]},idSubmissions:[],leaveRequests:[],employees:[],complaints:[],promotions:[],notifications:[],activity:[],auditLog:[]} as unknown as RawDataset);
}
interface LiveState {profile:LiveProfile|null;data:Dataset;loading:boolean;error:string;warnings:string[];currency:string;revision:number;employeeIds:Record<string,string>;raw:Record<string,unknown>;load:(org:string)=>Promise<void>;refresh:()=>Promise<void>;reset:()=>void;}
let epoch=0;
export const useLive=create<LiveState>((set,get)=>({profile:null,data:emptyDataset(),loading:false,error:"",warnings:[],currency:"USD",revision:0,employeeIds:{},raw:{},
 reset:()=>{epoch++;set({profile:null,data:emptyDataset(),loading:false,error:"",warnings:[],employeeIds:{},raw:{}});},
 refresh:async()=>{const p=get().profile;if(p)await get().load(p.organization_id);},
 load:async(org)=>{
  const run=++epoch,old=get().profile;
  set({loading:true,error:"",...(old?.organization_id!==org?{profile:null,data:emptyDataset(),raw:{},employeeIds:{}}:{})});
  try{
   const profile=await request("/api/v1/users/me","GET",undefined,org) as LiveProfile;
   if(!profile || profile.organization_id!==org || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(profile.user_id) || !displayRole[profile.role] || typeof profile.email!=="string")throw new Error("The backend returned an invalid membership contract");
   if(run!==epoch)return;
   const data=emptyDataset(),warnings:string[]=[],raw:Record<string,unknown>={};
   // Share initial requests and bound concurrency to avoid serial startup and DB overload.
   const pending=new Map<string,Promise<unknown>>();let active=0;const waiting:(()=>void)[]=[];
   const read=(path:string):Promise<unknown>=>{
    const cached=pending.get(path);if(cached)return cached;
    const result=(async()=>{if(active>=4)await new Promise<void>(resolve=>waiting.push(resolve));active++;
     try{return await request(path,"GET",undefined,org);}catch(e){if(e instanceof ApiError && e.status===401)throw e;warnings.push((e instanceof Error?e.message:"Data unavailable")+" · "+path);return undefined;}
     finally{active--;waiting.shift()?.();}
    })();pending.set(path,result);return result;
   };
   const initial=["/api/v1/organizations/current"];
   const initialList=(path:string)=>initial.push(path+"?limit=100&offset=0");
   if(["owner","senior_developer","junior_developer"].includes(profile.role))initialList("/api/v1/projects");
   if(profile.role==="hr"||profile.employee_id)initialList("/api/v1/hr/leave");
   if(profile.role==="hr")for(const path of ["/api/v1/employees","/api/v1/hr/payroll","/api/v1/hr/job-roles","/api/v1/hr/identity-documents"])initialList(path);
   if(profile.role==="owner"){initialList("/api/v1/finance/costs");initialList("/api/v1/finance/budgets");initial.push("/api/v1/finance/summary?currency="+get().currency);}
   if(profile.role==="security_analyst")for(const path of ["/api/v1/vader/incidents","/api/v1/vader/events","/api/v1/vader/anomalies"])initialList(path);
   if(["owner","security_analyst"].includes(profile.role))initialList("/api/v1/audit");
   await Promise.allSettled(initial.map(read));
   const list=async(path:string):Promise<Row[]>=>{
    const result:Row[]=[];
    for(let offset=0;offset<2000;offset+=100){const response=await read(path+(path.includes("?")?"&":"?")+"limit=100&offset="+offset);const value=Array.isArray(response)?response:row(response).items;if(!Array.isArray(value))return result;result.push(...rows(value));if(value.length<100)return result;}
    warnings.push("This view is limited to the first 2,000 accessible records.");return result;
   };
   const organization=row(await read("/api/v1/organizations/current"));
   data.id=org;data.org={name:str(organization.name,"Your organization"),domain:str(organization.domain),plan:"Connected workspace",region:""};
   const role=displayRole[profile.role];if(!role)throw new Error("Your membership role is not supported by this frontend");
   data.roleUsers[role]=profile.user_id;
   raw.organization=organization;
   const employeeIds:Record<string,string>={};
   const employeeRows=profile.role==="hr"?await list("/api/v1/employees"):[];
   data.employees=employeeRows.map(e=>{
    const uid=str(e.user_id);employeeIds[uid]=str(e.id);
    const memberRole=str(e.app_role),appRole=displayRole[memberRole] || (uid===profile.user_id?role:"" as Role);
    return {id:uid,name:str(e.name,"Team member"),email:str(e.email,uid===profile.user_id?profile.email:"Not available"),role:memberRole?memberRole.replaceAll("_"," "):"Role not provided",appRole,department:str(e.department) as Employee["department"],status:({active:"Active",onboarding:"Onboarding",offboarded:"Offboarded"} as Record<string,string>)[str(e.status)] || "Unknown",verification:({verified:"Verified",approved:"Verified",pending:"Pending review",rejected:"Needs resubmission"} as Record<string,string>)[str(e.verification_status)] || "Not submitted",joinDate:str(e.created_at),location:"Not provided",projects:[],trustScore:null,trustEvents:[],salaryBand:"Not provided",riskScore:Number.NaN} as Employee;
   });
   if(profile.role==="hr"){
    const departments=new Map<string,number>();for(const employee of employeeRows){const department=str(employee.department)||"Not recorded";departments.set(department,(departments.get(department)||0)+1);}
    data.departmentStats=[...departments].map(([dept,headcount])=>({dept,headcount,cloudSpend:Number.NaN,budget:Number.NaN})) as Dataset["departmentStats"];
   }
   if(profile.employee_id)employeeIds[profile.user_id]=profile.employee_id;
   if(profile.role!=="hr"&&!data.employees.some(e=>e.id===profile.user_id))data.employees.push({id:profile.user_id,name:profile.name||profile.owner_name||"Your account",email:profile.email,role:profile.role.replaceAll("_"," "),appRole:role,department:"" as Employee["department"],status:"Active",verification:"Not submitted",joinDate:"",location:"Not provided",projects:[],trustScore:null,trustEvents:[],salaryBand:"Not provided",riskScore:Number.NaN});
   if(["owner","senior_developer","junior_developer"].includes(profile.role)){
    const projects=await list("/api/v1/projects");raw.projects=projects;
    const taskRows:Row[]=[];const sprints:Row[]=[];
    for(const p of projects){taskRows.push(...await list("/api/v1/projects/"+p.id+"/tasks"));sprints.push(...await list("/api/v1/projects/"+p.id+"/sprints"));}
    const taskDetails=new Map<string,Row>();
    await Promise.all(taskRows.slice(0,100).map(async task=>{const detail=row(await read(`/api/v1/tasks/${task.id}/details`));if(detail.id===task.id)taskDetails.set(String(task.id),detail);}));
    raw.taskDetails=Object.fromEntries(taskDetails);
    if(taskRows.length>100)warnings.push("Task metadata beyond the first100 records is loaded when a task is opened.");
    const enrichedTasks:Row[]=taskRows.map(task=>({...task,...taskDetails.get(String(task.id)),metadataKnown:taskDetails.has(String(task.id))}));
    data.tasks=enrichedTasks.map(t=>({metadataKnown:t.metadataKnown,id:str(t.id),key:"TASK-"+str(t.id).slice(0,6).toUpperCase(),title:str(t.title),description:str(t.description),status:({todo:"To do",in_progress:"In progress",review:"In review",done:"Done"} as Record<string,string>)[str(t.status)] || "To do",priority:({low:"Low",normal:"Medium",high:"High",critical:"Critical"}[str(t.priority)]||"Medium"),assignee:str(t.assignee_id),projectId:str(t.project_id),points:0,labels:[],sprint:str(t.sprint_id),due:str(t.deadline),comments:[]} as Task));
    data.projects=projects.map(p=>{const ts=data.tasks.filter(t=>t.projectId===p.id);return {id:str(p.id),key:str(p.name).split(/\s+/).map(s=>s[0]).join("").slice(0,8).toUpperCase(),name:str(p.name),description:str(p.description),status:({approved:"Active",reviewed:"Awaiting approval",proposed:"Awaiting approval",rejected:"Rejected"} as Record<string,string>)[str(p.status)]||"Planning",priority:"Medium",progress:ts.length?Math.round(ts.filter(t=>t.status==="Done").length/ts.length*100):0,lead:str(p.proposer_id),members:[...new Set([str(p.proposer_id),...ts.map(t=>t.assignee)])],budget:Number.NaN,spent:Number.NaN,department:"" as Project["department"],dueDate:"",proposedBy:str(p.proposer_id),cloud:"" as Project["cloud"],repos:[]} as Project;});
    data.sprints=sprints.map(s=>({id:str(s.id),name:str(s.name),start:str(s.starts_on),end:str(s.ends_on),status:str(s.status),velocity:0})) as Dataset["sprints"];
    data.employees=data.employees.map(e=>({...e,projects:data.projects.filter(p=>p.members.includes(e.id)).map(p=>p.id)}));
   }
   if(profile.role==="hr" || profile.employee_id){
    const leave=await list("/api/v1/hr/leave");data.leaveRequests=leave.map(l=>({id:str(l.id),employee:str(employeeRows.find(e=>e.id===l.employee_id)?.user_id,profile.user_id),from:str(l.starts_on),to:str(l.ends_on),status:({pending:"Pending",approved:"Approved",rejected:"Rejected",cancelled:"Cancelled"} as Record<string,string>)[str(l.status)]||str(l.status),type:"Leave",days:Math.max(0,Math.round((Date.parse(str(l.ends_on))-Date.parse(str(l.starts_on)))/86400000)+1),reason:str(l.reason)})) as Dataset["leaveRequests"];
   }
   if(profile.role==="hr"){
    raw.payroll=await list("/api/v1/hr/payroll");raw.roles=await list("/api/v1/hr/job-roles");
    const documents=await list("/api/v1/hr/identity-documents");raw.documents=documents;
    data.idSubmissions=documents.map(d=>({id:str(d.id),employee:str(employeeRows.find(e=>e.id===d.employee_id)?.user_id),docType:str(d.media_type,"Identity image"),submittedAt:str(d.created_at),status:({pending_hr:"Pending review",pending:"Pending review",approved:"Approved",rejected:"Needs resubmission"} as Record<string,string>)[str(d.status)]||"Pending review",submitted:{name:"Not provided",dob:"Not provided",idNumber:"Not provided",expiry:"Not provided"},ocr:{name:"Not available",dob:"Not available",idNumber:"Not available",expiry:"Not available"},history:[],confidence:{name:Number.NaN,dob:Number.NaN,idNumber:Number.NaN,expiry:Number.NaN}})) as Dataset["idSubmissions"];
   }
   if(profile.role==="owner"){
    raw.costs=await list("/api/v1/finance/costs");raw.budgets=await list("/api/v1/finance/budgets");
    raw.finance=await read("/api/v1/finance/summary?currency="+get().currency);
    const costs=rows(raw.costs).filter(c=>c.currency===get().currency);
    const months=new Map<string,number>();for(const c of costs)months.set(str(c.period),(months.get(str(c.period))||0)+number(c.amount));
    data.monthlyCost=[...months].sort(([a],[b])=>a.localeCompare(b)).map(([month,actual])=>({month,actual,forecast:Number.NaN})) as Dataset["monthlyCost"];
    const departments=new Map<string,number>();for(const c of costs)departments.set(str(c.department),(departments.get(str(c.department))||0)+number(c.amount));
    data.departmentStats=[...departments].map(([dept,cloudSpend])=>({dept,cloudSpend,headcount:Number.NaN,budget:Number.NaN})) as Dataset["departmentStats"];
    data.orgKpis.monthlyCloudSpend=costs.filter(c=>c.category==="cloud"&&c.period===new Date().toISOString().slice(0,7)).reduce((s,c)=>s+number(c.amount),0);
   }
   if(profile.role==="security_analyst"){
    const incidents=await list("/api/v1/vader/incidents");raw.incidents=incidents;
    data.incidents=incidents.map(i=>({id:str(i.id),title:"Investigation: "+str(i.actor_id,"actor"),severity:number(i.risk)>=75?"critical":number(i.risk)>=50?"high":"medium",status:({open:"Open",triaged:"Investigating",contained:"Contained",resolved:"Resolved",false_positive:"Resolved"} as Record<string,string>)[str(i.status)] || "Open",detectedAt:str(i.created_at),summary:str(i.explanation),assets:[],analyst:profile.name||"Security team",riskBefore:number(i.risk),riskAfter:number(i.risk)} as Incident));
    raw.events=await list("/api/v1/vader/events");raw.anomalies=await list("/api/v1/vader/anomalies");
   }
   if(["owner","security_analyst"].includes(profile.role)){
    const entries=rows(await read("/api/v1/audit?limit=100&offset=0"));if(entries.length===100)warnings.push("Audit view shows the first 100 accessible records.");
    data.auditLog=entries.map(a=>({id:str(a.id),at:str(a.timestamp),actor:a.actor_id===profile.user_id?profile.name||"You":"Authorized member",action:str(a.action).replaceAll("."," "),target:str(a.target_id),module:"System",result:str(a.outcome)==="denied"?"Denied":"Success",ip:"Not collected"})) as Dataset["auditLog"];
   }
   data.orgKpis.totalEmployees=profile.role==="hr"?employeeRows.length:Number.NaN;data.orgKpis.securityPosture=Number.NaN;data.orgKpis.activeProjects=data.projects.filter(p=>p.status==="Active").length;data.orgKpis.pendingApprovals=data.projects.filter(p=>p.status==="Awaiting approval").length;data.orgKpis.openIncidents=data.incidents.filter(i=>i.status!=="Resolved").length;
   if(run!==epoch)return;
   set({profile,data:makeDataset(data),employeeIds,raw,warnings,loading:false,error:"",revision:get().revision+1});
  }catch(e){if(run===epoch)set({profile:null,data:emptyDataset(),raw:{},employeeIds:{},warnings:[],loading:false,error:e instanceof Error?e.message:"Workspace could not be loaded",revision:get().revision+1});}
 }
}));
