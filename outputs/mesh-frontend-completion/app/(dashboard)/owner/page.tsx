"use client";
import {isLive,useLive} from "@/lib/connected/live-state";
import { Briefcase, Cloud, ClipboardCheck, ShieldAlert, ShieldCheck, Users } from "lucide-react";
import { KpiCard } from "@/components/features/kpi-card";
import { WelcomeHero } from "@/components/features/owner/welcome-hero";
import { WhatIfStudio } from "@/components/features/owner/what-if-studio";
import { ActiveProjectsCard, AwaitingApprovals } from "@/components/features/owner/approvals";
import {
  BudgetForecastCard, CloudSpendCard, DepartmentSpendCard, ProviderSplitCard, UtilizationCard, useFinance,
} from "@/components/features/owner/finance-widgets";
import { TaskCompletionCard, TeamActivityCard, TrustBoardCard } from "@/components/features/owner/performance";
import { useWorkspace } from "@/stores/workspace-store";
import { fmtCurrency } from "@/lib/utils/format";
import { useDataset } from "@/lib/api";

export default function OwnerOverview() {
  const currency=useLive(s=>s.currency);
  const { kpiSparks, orgKpis, riskTrend } = useDataset();
  const { data } = useFinance();
  const pending = useWorkspace((s) => s.projects.filter((p) => p.status === "Awaiting approval").length);
  const openIncidents = useWorkspace((s) => s.incidents.filter((i) => i.status !== "Resolved").length);

  return (
    <div className="space-y-6">
      <WelcomeHero />

      <section aria-label="Key metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Total employees" value={orgKpis.totalEmployees} icon={Users} accent="violet" spark={kpiSparks.employees} variant="gradient" href="/people/directory" />
        <KpiCard label="Active projects" value={orgKpis.activeProjects} icon={Briefcase} accent="sky" spark={kpiSparks.projects} href="/owner/projects" />
        <KpiCard label="Monthly cloud spend" value={orgKpis.monthlyCloudSpend} format={(n) => fmtCurrency(n,false,currency)} delta={orgKpis.spendDelta} goodWhen="down" icon={Cloud} accent="amber" spark={kpiSparks.spend} href="/owner/finance" />
        <KpiCard label="Pending approvals" value={pending} icon={ClipboardCheck} accent="violet" spark={kpiSparks.approvals} href="/owner/projects" />
        <KpiCard label="Open security incidents" value={isLive()?Number.NaN:openIncidents} delta={orgKpis.incidentDelta} deltaLabel="vs last week" goodWhen="down" icon={ShieldAlert} accent="coral" spark={kpiSparks.incidents} href="/vader/incidents" />
        <KpiCard label="Security posture" value={orgKpis.securityPosture} suffix="/ 100" delta={riskTrend.length ? riskTrend[0].score - riskTrend[riskTrend.length - 1].score : undefined} deltaLabel="over seeded window" icon={ShieldCheck} accent="mint" spark={riskTrend.map((point) => 100 - point.score)} href="/vader" />
      </section>

      <WhatIfStudio />

      <section aria-label="Financial intelligence" className="space-y-4">
        <h2 className="font-display text-lg font-bold">Financial intelligence</h2>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2"><CloudSpendCard data={data} /></div>
          <ProviderSplitCard data={data} />
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <DepartmentSpendCard data={data} />
          <UtilizationCard data={data} />
          <BudgetForecastCard data={data} />
        </div>
      </section>

      <section aria-label="Projects and approvals" className="space-y-4">
        <h2 className="font-display text-lg font-bold">Projects and approvals</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <AwaitingApprovals limit={3} />
          <ActiveProjectsCard limit={4} />
        </div>
      </section>

      <section aria-label="Employee performance" className="space-y-4">
        <h2 className="font-display text-lg font-bold">Employee performance</h2>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="xl:col-span-1"><TrustBoardCard limit={5} /></div>
          <div className="xl:col-span-1"><TeamActivityCard /></div>
          <div className="xl:col-span-1"><TaskCompletionCard /></div>
        </div>
      </section>
    </div>
  );
}
