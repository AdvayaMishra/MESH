"use client";
import { useSyncExternalStore } from "react";
import Link from "next/link";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { CommandPalette } from "@/components/layout/command-palette";
import { RouteGuard, UIHydrator } from "@/components/layout/route-guard";
import { LiveShell } from "./live-shell";
export function PreviewDashboard({children}:{children:React.ReactNode}) {
  const mode=useSyncExternalStore(()=>()=>{},()=>sessionStorage.getItem("mesh-preview-mode") || "connected",()=>null);
  if(!mode) return <p className="p-8" aria-busy="true">Opening MESH preview…</p>;
  if(mode!=="demo") return <LiveShell>{children}</LiveShell>;
  return <><div className="sticky top-0 z-50 bg-tint-amber p-3 text-center text-sm"><strong>Visual demo · simulated data.</strong> Changes here are not saved to the backend. <Link href="/login" className="font-semibold underline">Open connected preview</Link></div><UIHydrator /><div className="flex min-h-dvh"><Sidebar /><div className="flex min-w-0 flex-1 flex-col"><Topbar /><main id="main" className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 sm:px-6 lg:px-8"><RouteGuard>{children}</RouteGuard></main></div></div><CommandPalette /></>;
}
