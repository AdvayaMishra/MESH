"use client";
import {useState} from "react";
import {usePathname} from "next/navigation";
import Link from "next/link";
import {Card,CardHeader,CardBody} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Field,Input,Textarea} from "@/components/ui/input";
import {useLive} from "./live-state";
import {request} from "./client";
import {DataUnavailable} from "./finance";
import {LiveInsight,LiveIncidentList,useResource,RecordTable} from "./security";
import {ErrorMessage,rows} from "./hr";
import {LiveOrganization,LiveSimulation,LiveRisk} from "./advanced";
import {LiveDirectoryControls,LiveIdentityUpload,LiveSprintManagement,LiveProjectMembers,LiveApprovalPolicy,LiveEmploymentAdministration} from "./supplemental";
import {LiveJobRoles,LiveAIUsage} from "./job-roles";
import {LiveTrustReview,LiveBudgetVariance,LiveBillingCollections} from "./advanced-actions";
import {LivePayrollCalculator} from "./payroll-calculator";
import {LivePayroll,LiveLeave,LiveLifecycle} from "./hr";
import {LiveVerification} from "./documents";
import {LiveSessions,LiveIncidentDetail,LiveInvestigation} from "./investigation";
import {LiveSecurityOverview,LiveSecurityEvidence,LiveCloud,LiveRepositorySecurity} from "./security";
import {LiveFinanceEntry,LiveWhatIf,LiveFinanceCard,LiveFinanceCurrency} from "./finance";
import {LiveComplaints} from "./complaints";
type Row=Record<string,unknown>;
function ProjectDetail({id}:{id:string}){const live=useLive(),project=live.data.projects.find(p=>p.id===id),record=rows(live.raw.projects).find(p=>p.id===id),comments=useResource(`/api/v1/projects/${id}/comments?limit=100`);const [error,setError]=useState(""),[busy,setBusy]=useState(false);
 async function decision(value:string){setBusy(true);setError("");try{await request(`/api/v1/projects/${id}/${value==="review"?"reviews":"decision"}`,"POST",value==="review"?{comment:"Reviewed through the connected workspace"}:{decision:value},live.profile?.organization_id);await live.refresh();}catch(e){setError(e instanceof Error?e.message:"Project decision could not be saved");}finally{setBusy(false);}}
 if(!project)return <DataUnavailable title="Project unavailable" reason="This project is not in your accessible records. Refresh your workspace or check its reference."/>;
 return <div className="space-y-6"><Card><CardHeader title={project.name} subtitle={`Backend status: ${String(record?.status)}`}/><CardBody><p className="text-sm text-ink-2">{project.description||"No goal has been provided."}</p><p className="mt-4 text-sm">Tasks completed: {live.data.tasks.filter(t=>t.projectId===id&&t.status==="Done").length} of {live.data.tasks.filter(t=>t.projectId===id).length}</p><ErrorMessage error={error}/><div className="mt-4 flex flex-wrap gap-3">{live.profile?.role==="senior_developer"&&<Button disabled={busy||project.proposedBy===live.profile.user_id} onClick={()=>void decision("review")}>Submit independent review</Button>}{live.profile?.role==="owner"&&<><Button disabled={busy||record?.status!=="reviewed"} onClick={()=>void decision("approved")}>Approve reviewed project</Button><Button variant="secondary" disabled={busy||!["proposed","reviewed"].includes(String(record?.status))} onClick={()=>void decision("rejected")}>Reject proposal</Button></>}<Button asChild variant="secondary"><Link href="/devtrack/board">Open task board</Link></Button></div><p className="mt-3 text-xs text-ink-3">Budgets, provider choice, estimated deadlines and historical activity are not inferred from project records.</p></CardBody></Card><LiveProjectMembers projectId={id}/><Card><CardHeader title="Project comments"/><CardBody><ErrorMessage error={comments.error}/><RecordTable data={rows(comments.data)} columns={[["created_at","Written"],["body","Comment"],["author_id","Author reference"]]}/><form className="mt-4 space-y-3" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);setBusy(true);setError("");try{await request(`/api/v1/projects/${id}/comments`,"POST",{body:data.get("body")},live.profile?.organization_id);form.reset();comments.refresh();}catch(e){setError(e instanceof Error?e.message:"Comment could not be saved");}finally{setBusy(false);}}}><Field label="Project comment" htmlFor="project-comment"><Textarea id="project-comment" name="body" required maxLength={4000}/></Field><Button disabled={busy}>Save comment</Button></form></CardBody></Card></div>;
}
function EmployeeDetail({id}:{id:string}){const employee=useLive(s=>s.data.employeeById(id));return employee?<Card><CardHeader title={employee.name} subtitle={employee.role}/><CardBody><dl className="grid gap-4 text-sm sm:grid-cols-2">{[["Email",employee.email],["Department",employee.department],["Status",employee.status],["Verification",employee.verification],["Location",employee.location]].map(([label,value])=><div key={label}><dt className="text-ink-3">{label}</dt><dd>{value||"Not available"}</dd></div>)}</dl><p className="mt-5 text-xs text-ink-3">Compensation, identity documents and lifecycle changes require their dedicated HR workflows.</p></CardBody></Card>:<DataUnavailable title="Employee unavailable" reason="This employee is not in your accessible directory."/>;}
function Trust(){const live=useLive();const [user,setUser]=useState(live.profile?.user_id||""),[selected,setSelected]=useState("");const result=useResource(selected?`/api/v1/trust/${selected}`:""),data=result.data as Row|null;return <Card><CardHeader title="Trust Stars" subtitle="Human decision support, never an automatic employment or enforcement decision."/><CardBody><form className="flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();setSelected(user);result.refresh();}}><Field label="Employee user reference" htmlFor="trust-user"><Input id="trust-user" required pattern="[a-fA-F0-9-]{36}" value={user} onChange={e=>setUser(e.target.value)}/></Field><Button>Load reviewed score</Button></form><ErrorMessage error={result.error}/>{data&&<div className="mt-5"><p className="font-display text-2xl font-bold">{String(data.score)} / 50 · {String(data.stars)} stars</p><RecordTable data={rows(data.events)} columns={[["delta","Change"],["reason","Reviewed reason"]]}/></div>}<p className="mt-3 text-xs text-ink-3">Owner and HR memberships are not scored. The backend enforces access to other employees&apos; scores.</p></CardBody></Card>;}
export function LiveContent({children}:{children:React.ReactNode}){const path=usePathname(),live=useLive();const unavailable:Record<string,[string,string]>={
 "/workspace/notifications":["Notifications","Notification delivery and read-status APIs are not available in the current backend."],
 "/workspace/reports":["Reports","Report generation and scheduled exports are not implemented in the current backend. The employee directory can export the records you can access."],
 "/workspace/activity":["Activity","A combined activity-feed API is not available. Owners and security analysts can review the actual audit log."],
 "/devtrack/pull-requests":["Pull requests","Pull request review and merge controls are not implemented in this backend. Repository scanning is available in Security."],
 };
 if(live.profile?.role!=="hr"&&["/people","/people/directory","/people/verification","/people/payroll","/people/administration","/people/promotions"].includes(path))return <DataUnavailable title="HR access required" reason="The current backend restricts employee records, payroll and private document review to HR. No employee totals or records are inferred."/>;
 if(path==="/people/payroll")return <div className="space-y-6"><LivePayroll/><LivePayrollCalculator/></div>;
 if(path==="/people/leave"||path==="/people/leave/review"||path==="/workspace/leave")return <LiveLeave/>;
 if(path==="/people/lifecycle")return <LiveLifecycle/>;
 if(path==="/people/promotions")return <div className="space-y-4"><LiveJobRoles/><LiveEmploymentAdministration/></div>;
 if(path==="/people/verification")return <LiveVerification/>;
 if(path==="/people/administration")return <><LiveDirectoryControls/><LiveJobRoles/><LiveEmploymentAdministration/><LiveLifecycle/></>;
 if(path==="/people/directory")return <><LiveDirectoryControls/>{children}</>;
 if(path==="/workspace/settings")return <><LiveSessions/><LiveIdentityUpload/></>;
 if(path==="/devtrack/security")return <LiveRepositorySecurity/>;
 if(path==="/devtrack/sprints")return <LiveSprintManagement/>;
 if(path==="/vader")return <LiveSecurityOverview/>;
 if(path==="/vader/behavior")return <LiveSecurityEvidence/>;
 if(path==="/vader/cloud")return <LiveCloud/>;
 if(path==="/vader/attack-chain")return <LiveInvestigation/>;
 if(/^\/vader\/incidents\/[^/]+$/.test(path))return <LiveIncidentDetail/>;
 if(path==="/vader/copilot")return <LiveInsight/>;
 if(path==="/owner/finance")return <div className="space-y-6"><LiveFinanceCurrency/><LiveFinanceEntry/><LiveBudgetVariance/><LiveBillingCollections/><div className="grid gap-4 lg:grid-cols-2"><LiveFinanceCard kind="cloud"/><LiveFinanceCard kind="department"/><LiveFinanceCard kind="budget"/><LiveFinanceCard kind="provider"/></div><LiveWhatIf/></div>;
 if(path==="/vader/incidents")return <LiveIncidentList/>;
 if(path==="/workspace/complaints"||path==="/people/complaints")return <LiveComplaints/>;
 if(unavailable[path])return <DataUnavailable title={unavailable[path][0]} reason={unavailable[path][1]}/>;
 if(path==="/workspace/organization")return <><LiveOrganization/><LiveApprovalPolicy/></>;
 if(path==="/vader/simulation")return <LiveSimulation/>;
 if(path==="/vader/risk")return <LiveRisk/>;
 if(path==="/workspace/trust")return <div className="space-y-6"><Trust/><LiveTrustReview/></div>;
 if(path==="/workspace/insights")return <div className="space-y-6">{["owner","hr","security_analyst"].includes(live.profile?.role||"")?<LiveInsight scope={live.profile?.role==="owner"?"owner":live.profile?.role==="hr"?"hr":"vader"}/>:<LiveInsight scope="devtrack"/>}<LiveAIUsage/></div>;
 if(path==="/owner/performance")return <Card><CardHeader title="Current task completion" subtitle="Saved project task states; historical performance is not inferred."/><CardBody><RecordTable data={live.data.projects.map(p=>({id:p.id,name:p.name,total:live.data.tasks.filter(t=>t.projectId===p.id).length,done:live.data.tasks.filter(t=>t.projectId===p.id&&t.status==="Done").length}))} columns={[["name","Project"],["total","Tasks"],["done","Done"]]}/></CardBody></Card>;
 const project=path.match(/^\/devtrack\/projects\/([^/]+)$/);if(project)return <ProjectDetail id={project[1]}/>;
 const employee=path.match(/^\/people\/directory\/([^/]+)$/);if(employee)return <EmployeeDetail id={employee[1]}/>;
 return children;
}
