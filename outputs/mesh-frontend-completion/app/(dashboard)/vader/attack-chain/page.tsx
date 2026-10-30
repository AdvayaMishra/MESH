"use client";
import { PageHeader } from "@/components/features/page-header";
import { ChainExplorer } from "@/components/features/vader/chain-detail";
import { SimulatedTag } from "@/components/ui/badge";

export default function AttackChainPage() {
  return (
    <div>
      <PageHeader title="Attack-chain correlation" description="Scattered alerts joined into one timeline. Select a step to see the evidence behind it." badge={<SimulatedTag label="Seeded incident" />} />
      <ChainExplorer graphHeight={420} />
    </div>
  );
}
