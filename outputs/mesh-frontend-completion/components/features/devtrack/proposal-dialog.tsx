"use client";
import { isLive } from "@/lib/connected/live-state";
import { mutations, liveResult } from "@/lib/connected/mutations";

import { useDataset } from "@/lib/api";
import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { useWorkspace } from "@/stores/workspace-store";
import type { Project } from "@/lib/types";

const schema = z.object({
  name: z.string().min(3, "Give the project a name"),
  description: z.string().min(20, "Describe the goal in at least 20 characters"),
  budget: z.coerce.number().min(1000, "Budget must be at least $1,000"),
  priority: z.enum(["Critical", "High", "Medium", "Low"]),
  cloud: z.enum(["AWS", "Azure", "GCP"]),
  due: z.string().min(1, "Choose a target date"),
});
type Values = z.input<typeof schema>;

export function ProposalDialog({ open, onOpenChange, proposer: proposerProp }: { open: boolean; onOpenChange: (o: boolean) => void; proposer?: string }) {
  const { currentUser } = useDataset();
  const proposer = proposerProp ?? currentUser.id;
  const { addProject } = useWorkspace();
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<Values, unknown, z.output<typeof schema>>({
    resolver: zodResolver(isLive()?schema.extend({due:z.string()}):schema),
    defaultValues: { name: "", description: "", budget: 25000, priority: "Medium", cloud: "AWS", due: "" },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Propose a project" description={isLive()?"Save the project name and goal for independent review. Budgets and schedules use separate backend workflows.":"Submit a simulated proposal for an owner decision."}>
        <form
          noValidate
          className="space-y-4"
          onSubmit={handleSubmit(async (v) => {
            if(!isLive())await new Promise((r) => setTimeout(r, 500));
            const unique = crypto.randomUUID();
            const id = `PRJ-${unique}`;
            const p: Project = {
              id, key: `${v.name.replace(/[^A-Za-z]/g, "").slice(0, 5).toUpperCase() || "NEW"}-${unique.slice(0, 6).toUpperCase()}`, name: v.name, description: v.description, status: "Awaiting approval",
              priority: v.priority, progress: 0, lead: proposer, members: [proposer], budget: v.budget, spent: 0, department: "Engineering", dueDate: v.due, proposedBy: proposer, proposedAt: new Date().toISOString().slice(0, 10), cloud: v.cloud, repos: [],
            };
            const result = isLive()?await liveResult(()=>mutations.addProject(p)):addProject(p);
            if (!result.ok) { toast.error(result.error); return; }
            toast.success(isLive()?"Proposal saved":"Proposal submitted (simulated)", { description: `${v.name} is now awaiting approval.` });
            reset();
            onOpenChange(false);
          })}
        >
          <Field label="Project name" htmlFor="pname" error={errors.name?.message}><Input id="pname" aria-invalid={!!errors.name} {...register("name")} /></Field>
          <Field label="What will it achieve?" htmlFor="pdesc" error={errors.description?.message}><Textarea id="pdesc" aria-invalid={!!errors.description} {...register("description")} /></Field>
          {!isLive()&&<div className="grid gap-4 sm:grid-cols-2">
            <Field label="Budget (USD)" htmlFor="pbudget" error={errors.budget?.message}><Input id="pbudget" type="number" min={0} aria-invalid={!!errors.budget} {...register("budget")} /></Field>
            <Field label="Target date" htmlFor="pdue" error={errors.due?.message}><Input id="pdue" type="date" aria-invalid={!!errors.due} {...register("due")} /></Field>
            <Field label="Priority" htmlFor="pprio"><Select id="pprio" {...register("priority")}>{["Critical", "High", "Medium", "Low"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
            <Field label="Cloud provider" htmlFor="pcloud"><Select id="pcloud" {...register("cloud")}>{["AWS", "Azure", "GCP"].map((p) => <option key={p}>{p}</option>)}</Select></Field>
          </div>}
          <div className="flex justify-end gap-2 pt-2"><Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" variant="gradient" disabled={isSubmitting||(isLive()&&!["senior_developer","junior_developer"].includes(currentUser.role))}>{isSubmitting ? "Submitting…" : "Submit proposal"}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
