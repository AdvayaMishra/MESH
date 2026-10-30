"use client";
import { useEffect,useState } from "react";
export function usePreviewInfo() {
  const [info,setInfo]=useState<{mode:string;organization_id:string|null;dedicated_accounts_available?:boolean}>({mode:"loading",organization_id:null});
  useEffect(()=>{let active=true;fetch("/api/preview-info",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("Preview mode unavailable");return r.json();}).then(v=>{if(active)setInfo(v);}).catch(()=>{if(active)setInfo({mode:"unavailable",organization_id:null});});return()=>{active=false;};},[]);
  return info;
}
