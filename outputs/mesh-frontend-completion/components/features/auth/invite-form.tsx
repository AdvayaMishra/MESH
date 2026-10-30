"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Mail, Building2, UserCog } from "lucide-react";
import { AuthShell } from "@/components/features/auth/auth-shell";
import { employeeSteps } from "@/components/features/auth/stepper";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { PasswordField, PasswordMeter, passwordScore } from "@/components/features/auth/password-field";
import { useDataset } from "@/lib/api";
import { useUI } from "@/stores/ui-store";
import { useTenant } from "@/stores/tenant-store";
import { usePreferences } from "@/stores/preferences-store";

const schema = z.object({
  name: z.string().min(2, "Enter your full name"),
  password: z.string().min(10, "Use at least 10 characters").refine((v) => passwordScore(v) >= 3, "Add a number, a symbol or mixed case"),
  terms: z.boolean().refine((v) => v, "Accept the terms to continue"),
});

export function InviteForm({ kind }: { kind: "hr" | "employee" }) {
  const { org, employees, roleUsers } = useDataset();
  const invitee = kind === "hr" ? employees.find((e) => e.id === roleUsers.hr) : (employees.find((e) => e.status === "Onboarding") ?? employees[employees.length - 1]);
  const router = useRouter();
  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: invitee?.name ?? "", password: "", terms: false },
  });
  const email = invitee?.email ?? "";
  return (
    <AuthShell
      title={kind === "hr" ? "Join as HR administrator" : "Accept your invitation"}
      subtitle={`You’ve been invited to ${org.name} on MESH.`}
      steps={kind === "employee" ? employeeSteps : undefined}
      current={kind === "employee" ? 0 : undefined}
      simulated
    >
      <div className="mb-5 rounded-2xl border border-line bg-white p-4">
        <div className="flex items-center gap-3 text-sm">
          <span className="flex size-10 items-center justify-center rounded-xl bg-tint-violet text-indigo">{kind === "hr" ? <UserCog className="size-5" /> : <Building2 className="size-5" />}</span>
          <div>
            <p className="font-semibold text-ink">{kind === "hr" ? "HR administrator" : `Employee · ${invitee?.role ?? "Employee"}, ${invitee?.department ?? "Unassigned"}`}</p>
            <p className="flex items-center gap-1.5 text-ink-2"><Mail className="size-3.5" />{email}</p>
          </div>
        </div>
      </div>
      <form noValidate className="space-y-4" onSubmit={handleSubmit(async (value) => {
        const orgId = useTenant.getState().orgId;
        await new Promise((r) => setTimeout(r, 600));
        if (useTenant.getState().orgId !== orgId) return;
        if (invitee) {
          usePreferences.getState().saveProfile(orgId, invitee.appRole, { name: value.name, email: invitee.email, role: invitee.role }, invitee.id);
          if (kind === "hr") {
            usePreferences.getState().selectPersona(orgId, "hr", invitee.id);
            useUI.getState().setRole("hr");
          }
        }
        router.push(kind === "hr" ? "/people" : "/invite/employee/id-upload");
      })}>
        <Field label="Full name" htmlFor="name" error={errors.name?.message}><Input id="name" autoComplete="name" aria-invalid={!!errors.name} {...register("name")} /></Field>
        <Field label="Create a password" htmlFor="password" error={errors.password?.message}>
          <PasswordField id="password" autoComplete="new-password" aria-invalid={!!errors.password} {...register("password")} />
          <PasswordMeter value={watch("password")} />
        </Field>
        <div>
          <label className="flex items-start gap-3 text-sm text-ink-2">
            <input type="checkbox" className="mt-0.5 size-4 accent-violet" {...register("terms")} />
            I agree to the terms of service and privacy policy.
          </label>
          {errors.terms && <p role="alert" className="mt-1 text-xs text-[#d6294f]">{errors.terms.message}</p>}
        </div>
        <Button type="submit" variant="gradient" size="lg" className="w-full" disabled={isSubmitting}>{isSubmitting ? "Accepting…" : kind === "hr" ? "Accept and go to People" : "Accept and continue"}</Button>
      </form>
    </AuthShell>
  );
}
