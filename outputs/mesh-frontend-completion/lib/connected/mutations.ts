"use client";
import {request} from "./client";
import {useLive} from "./live-state";
import type {Project,Task,ProjectStatus,TaskStatus,FindingStatus,Incident} from "@/lib/types";
const taskStatus:Record<TaskStatus,string>={Backlog:"todo","To do":"todo","In progress":"in_progress","In review":"review",Done:"done"};
async function save(path:string,method:string,body:unknown){const live=useLive.getState();if(!live.profile)throw new Error("Sign in again to save changes");await request(path,method,body,live.profile.organization_id);if(useLive.getState().profile?.organization_id!==live.profile.organization_id)throw new Error("The organization changed after submission. Check the original organization before retrying.");await live.refresh();if(useLive.getState().error)throw new Error("The change was accepted, but the refreshed view is unavailable. Refresh before trying again.");}
export const mutations={
 async addProject(p:Project){await save("/api/v1/projects","POST",{name:p.name,description:p.description});},
 async setProjectStatus(id:string,status:ProjectStatus,note:string){const role=useLive.getState().profile?.role;if(role==="senior_developer"&&status!=="Rejected")await save(`/api/v1/projects/${id}/reviews`,"POST",{comment:note});else await save(`/api/v1/projects/${id}/decision`,"POST",{decision:status==="Rejected"?"rejected":"approved"});},
 async addTask(t:Task){await save("/api/v1/tasks","POST",{project_id:t.projectId,assignee_id:t.assignee,title:t.title});},
 async setTaskStatus(id:string,status:TaskStatus){await save("/api/v1/tasks/"+id,"PATCH",{status:taskStatus[status]});},
 async setFindingStatus(id:string,status:FindingStatus){await save("/api/v1/findings/"+id,"PATCH",{status:({Open:"open","In progress":"investigating",Fixed:"resolved","Accepted risk":"accepted_risk"} as Record<string,string>)[status]});},
 async setIncidentStatus(id:string,status:Incident["status"]){await save("/api/v1/vader/incidents/"+id,"PATCH",{status:({Open:"open",Investigating:"triaged",Contained:"contained",Resolved:"resolved"} as Record<string,string>)[status]});},
 async decideLeave(id:string,status:"Approved"|"Rejected"){await save(`/api/v1/hr/leave/${id}/decision`,"POST",{decision:status.toLowerCase()});},
 async decideId(id:string,status:string){await save(`/api/v1/hr/identity-documents/${id}/decision`,"POST",{decision:status==="Approved"?"approved":"rejected"});},
 async assignTask(){throw new Error("Changing the assignee of an existing task is not supported by the backend yet.");},
 async updateTask(id:string,patch:Partial<Task>){const task=useLive.getState().data.tasks.find(t=>t.id===id);if(!task)throw new Error("Task is not in your accessible records");
 if((patch.title!==undefined&&patch.title!==task.title)||(patch.description!==undefined&&patch.description!==task.description)||(patch.points!==undefined&&patch.points!==task.points)||(patch.labels!==undefined&&JSON.stringify(patch.labels)!==JSON.stringify(task.labels)))throw new Error("This backend supports task status, priority, deadline and sprint updates; other edits are unavailable.");
 if((patch.due===""&&task.due)||(patch.sprint==="Backlog"&&task.sprint))throw new Error("Existing deadlines and sprint assignments cannot be cleared through the current service.");
 await save("/api/v1/tasks/"+id,"PATCH",{status:taskStatus[task.status],priority:({Low:"low",Medium:"normal",High:"high",Critical:"critical"} as Record<string,string>)[patch.priority||task.priority],deadline:patch.due?new Date(patch.due+"T00:00:00Z").toISOString():null,sprint_id:patch.sprint&&patch.sprint!=="Backlog"?patch.sprint:null});},
 async addComment(){throw new Error("Task comments are not supported by the backend yet. Project comments are available separately.");},
 async addNotification(){throw new Error("Notifications are not configured on the backend.");},
 async markNotification(){throw new Error("Notification read status is not configured on the backend.");},
 async markAllNotifications(){throw new Error("Notification read status is not configured on the backend.");},
};

export async function liveResult(action:()=>Promise<void>):Promise<{ok:true}|{ok:false;error:string}>{try{await action();return {ok:true};}catch(error){return {ok:false,error:error instanceof Error?error.message:"The change could not be saved"};}}
