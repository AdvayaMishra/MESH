"use client";
import { BudgetPlanner } from "@/components/features/owner/budget-planner";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { downloadCsv } from "@/lib/export/csv";
import { PageHeader } from "@/components/features/page-header";
import { Button } from "@/components/ui/button";
import { SimulatedTag } from "@/components/ui/badge";
import { WhatIfStudio } from "@/components/features/owner/what-if-studio";
import {
  BudgetForecastCard, CloudSpendCard, DepartmentSpendCard, ProviderSplitCard, UtilizationCard, useFinance,
} from "@/components/features/owner/finance-widgets";

export default function FinancePage() {
  const { data } = useFinance();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Finance"
        description="Cloud expenditure, department budgets and forecasts across AWS, Azure and GCP."
        badge={<SimulatedTag label="Mock billing data" />}
        actions={
          <Button variant="secondary" disabled={!data} onClick={() => { if (!data) return; downloadCsv("mesh-finance-demo.csv", ["Month", "Actual spend", "Forecast spend"], data.monthlyCost.map((m) => [m.month, m.actual, m.forecast])); toast.success("Demo finance CSV downloaded", { description: "Contains simulated spending data only." }); }}>
            <Download /> Export CSV
          </Button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2"><CloudSpendCard data={data} /></div>
        <ProviderSplitCard data={data} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <DepartmentSpendCard data={data} />
        <UtilizationCard data={data} />
      </div>
      <BudgetForecastCard data={data} />
      <WhatIfStudio />
    <BudgetPlanner />
    </div>
  );
}
