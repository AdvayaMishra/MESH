"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AuthShell } from "@/components/features/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { PasswordField } from "@/components/features/auth/password-field";
import { roleLabels } from "@/lib/nav";
import { ALL_ROLES, roleHome } from "@/lib/permissions";
import { useUI } from "@/stores/ui-store";
import type { Role } from "@/lib/types";

const schema = z.object({ email: z.string().email("Enter a valid email"), password: z.string().min(1, "Enter your password") });
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const setRole = useUI((s) => s.setRole);
  const [role, setRoleLocal] = React.useState<Role>("owner");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "alex@lumenrobotics.io", password: "" } });

  return (
    <AuthShell title="Welcome back" subtitle="Log in to your MESH workspace." simulated footer={<>New to MESH? <Link href="/register" className="font-semibold text-indigo hover:underline">Create an organization</Link></>}>
      <form
        noValidate
        className="space-y-4"
        onSubmit={handleSubmit(async () => {
          await new Promise((r) => setTimeout(r, 700));
          sessionStorage.setItem("mesh-preview-mode", "demo");
          setRole(role);
          router.push(roleHome[role]);
        })}
      >
        <Field label="Email" htmlFor="email" error={errors.email?.message}><Input id="email" type="email" autoComplete="email" aria-invalid={!!errors.email} {...register("email")} /></Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message}>
          <PasswordField id="password" autoComplete="current-password" placeholder="Any password works in the prototype" aria-invalid={!!errors.password} {...register("password")} />
        </Field>
        <div className="flex justify-end"><Link href="/forgot-password" className="text-sm font-medium text-indigo hover:underline">Forgot password?</Link></div>
        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink">Sign in as (demo)</legend>
          <div className="flex flex-wrap gap-2">
            {ALL_ROLES.map((r) => (
              <label key={r} className={`cursor-pointer rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors ${role === r ? "border-violet bg-tint-violet text-indigo" : "border-line-strong text-ink-2 hover:border-violet/40"}`}>
                <input type="radio" name="role" className="sr-only" checked={role === r} onChange={() => setRoleLocal(r)} />
                {roleLabels[r]}
              </label>
            ))}
          </div>
        </fieldset>
        <Button type="submit" variant="gradient" size="lg" className="w-full" disabled={isSubmitting}>{isSubmitting ? "Signing in…" : "Log in"}</Button>
      </form>
    </AuthShell>
  );
}
