"use client";
import * as React from "react";
import { toast } from "sonner";
import { motion, useReducedMotion } from "framer-motion";
import { BadgeCheck, Check, FolderGit2, GitBranch, Loader2, ScanSearch, Search, ShieldCheck, Trash2 } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { cn } from "@/lib/utils/cn";
import { useWorkspace } from "@/stores/workspace-store";

const stages = [
  { id: "auth", label: "Authorized repository", icon: ShieldCheck, detail: "Checking demo authorization state" },
  { id: "clone", label: "Temporary clone", icon: GitBranch, detail: "Illustrative step; no clone is made" },
  { id: "scan", label: "Local scan", icon: Search, detail: "Illustrative step; no scanners are run" },
  { id: "find", label: "Findings", icon: ScanSearch, detail: "Seeded findings are displayed" },
  { id: "clean", label: "Cleanup", icon: Trash2, detail: "Illustrative cleanup; no files were created" },
];

export function ScanExperience({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const repos = useWorkspace((s) => s.repos);
  const reduce = useReducedMotion();
  const [repo, setRepo] = React.useState(repos[0]?.name ?? "");
  const [stage, setStage] = React.useState(-1);
  const completeDemoScan = useWorkspace((s) => s.completeDemoScan);
  const [runId, setRunId] = React.useState("");
  const recorded = React.useRef("");
  const target = repos.find((r) => r.name === repo);
  const running = stage >= 0 && stage < stages.length;
  const complete = stage >= stages.length;
  const blocked = !target?.authorized;

  React.useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => setStage((s) => s + 1), reduce ? 250 : 1100);
    return () => clearTimeout(t);
  }, [stage, running, reduce]);

  React.useEffect(() => {
    if (!complete || !runId || recorded.current === runId) return;
    recorded.current = runId;
    const result = completeDemoScan(repo, runId);
    if (!result.ok) toast.error(result.error);
  }, [complete, runId, repo, completeDemoScan]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setStage(-1); onOpenChange(o); }}>
      <DialogContent title="Scan a repository" description="This is a simulation. No repository is cloned and no scanner is run." className="max-w-xl">
        <div className="space-y-5">
          <div className="flex items-end gap-3">
            <label className="flex-1 space-y-1.5 text-[13px] font-medium">Repository
              <Select value={repo} onChange={(e) => { setRepo(e.target.value); setStage(-1); }} disabled={running} className="mt-1.5">
                {repos.map((r) => <option key={r.name} value={r.name}>{r.name}{r.authorized ? "" : " (not authorized)"}</option>)}
              </Select>
            </label>
            <Button variant="gradient" className="h-11" disabled={running || blocked} onClick={() => { setRunId(`SIM-SCAN-${crypto.randomUUID()}`); setStage(0); }}>{running ? <Loader2 className="animate-spin" /> : <ScanSearch />}{complete ? "Scan again" : "Start scan"}</Button>
          </div>

          <div className={cn("flex items-center justify-between rounded-xl border px-4 py-3 text-sm", blocked ? "border-coral/40 bg-tint-coral" : "border-mint/40 bg-tint-mint")}>
            <span className="flex items-center gap-2 font-medium"><FolderGit2 className="size-4" />{repo}</span>
            {blocked ? <Badge tone="coral" dot>Authorization revoked</Badge> : <Badge tone="mint" dot>Authorized by owner</Badge>}
          </div>
          {blocked && <p className="text-[13px] text-[#9d1a3c]">This repository can’t be scanned until an owner re-authorizes access from Organization settings.</p>}

          <ol className="space-y-0">
            {stages.map((s, i) => {
              const done = stage > i;
              const active = stage === i;
              return (
                <li key={s.id} className="relative flex gap-4 pb-5 last:pb-0">
                  {i < stages.length - 1 && <span className={cn("absolute left-[19px] top-10 h-[calc(100%-28px)] w-0.5", done ? "bg-mint" : "bg-line")} />}
                  <motion.span
                    animate={active && !reduce ? { scale: [1, 1.08, 1] } : { scale: 1 }}
                    transition={{ repeat: active ? Infinity : 0, duration: 1.2 }}
                    className={cn("relative z-10 flex size-10 shrink-0 items-center justify-center rounded-full border-2 bg-white", done ? "border-mint bg-mint text-white" : active ? "border-violet text-violet" : "border-line-strong text-ink-3")}
                  >
                    {done ? <Check className="size-4" /> : <s.icon className="size-4" />}
                  </motion.span>
                  <div className="pt-1.5">
                    <p className={cn("text-sm font-semibold", !done && !active && "text-ink-3")}>{s.label}</p>
                    <p className="text-xs text-ink-2">{active ? s.detail : done ? "Done" : "Waiting"}</p>
                  </div>
                </li>
              );
            })}
          </ol>

          {complete && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-2.5 rounded-2xl bg-canvas p-4 text-sm" aria-live="polite">
              <div className="flex items-center justify-between"><span className="flex items-center gap-2 font-semibold"><BadgeCheck className="size-4 text-mint" />Scan finished</span><SimulatedTag label="Simulated scan" /></div>
              <p className="text-ink-2">{target?.openFindings ?? 0} seeded open findings in {repo}. No new findings were generated.</p>
              <p className="flex items-center gap-2 text-[13px] font-medium text-[#008068]"><Trash2 className="size-4" /> No repository files were accessed or created.</p>
            </motion.div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
