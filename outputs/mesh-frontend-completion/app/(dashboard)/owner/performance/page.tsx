"use client";
import { PageHeader } from "@/components/features/page-header";
import { ContributionTable, TaskCompletionCard, TeamActivityCard, TrustBoardCard, TrustExplainer } from "@/components/features/owner/performance";

export default function PerformancePage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Team performance" description="Activity, contribution and Trust Stars, always with context and human review." />
      <TrustExplainer />
      <div className="grid gap-4 lg:grid-cols-2">
        <TeamActivityCard />
        <TaskCompletionCard />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
        <TrustBoardCard limit={8} />
        <ContributionTable />
      </div>
    </div>
  );
}
