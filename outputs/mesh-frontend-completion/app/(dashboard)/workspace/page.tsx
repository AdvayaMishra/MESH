"use client";
import {useEffect} from "react";
import {useRouter} from "next/navigation";
import {useLive,displayRole,isLive} from "@/lib/connected/live-state";
import {roleHome} from "@/lib/permissions";
export default function WorkspaceIndex(){const router=useRouter(),profile=useLive(s=>s.profile);useEffect(()=>{if(isLive()&&profile)router.replace(roleHome[displayRole[profile.role]]);else if(!isLive())router.replace("/workspace/notifications");},[profile,router]);return <p aria-busy="true">Opening your workspace…</p>;}
