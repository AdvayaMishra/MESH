import Link from "next/link";
import { Logo } from "@/components/layout/logo";
import { ShieldCheck } from "lucide-react";
import { Stepper, type Step } from "@/components/features/auth/stepper";
import { SimulatedTag } from "@/components/ui/badge";

export function AuthShell({
  children,
  title,
  subtitle,
  steps,
  current,
  simulated = true,
  wide,
  footer,
}: {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  steps?: Step[];
  current?: number;
  simulated?: boolean;
  wide?: boolean;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-10 lg:px-16">
        <Link href="/" aria-label="MESH home" className="w-fit"><Logo /></Link>
        <div className="mx-auto flex w-full flex-1 flex-col justify-center py-10" style={{ maxWidth: wide ? 620 : 440 }}>
          {steps && current !== undefined && <Stepper steps={steps} current={current} className="mb-8" />}
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-display text-[28px] font-extrabold leading-tight text-ink sm:text-[32px]">{title}</h1>
          </div>
          {subtitle && <p className="mt-2 text-[15px] text-ink-2">{subtitle}</p>}
          {simulated && (
            <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-dashed border-amber/60 bg-tint-amber px-3.5 py-2.5 text-[13px] text-[#8a5200]">
              <SimulatedTag className="mt-px shrink-0" />
              <span>This step is simulated. No email, DNS record or file is actually checked, and nothing is stored on a server.</span>
            </div>
          )}
          <div className="mt-7">{children}</div>
          {footer && <div className="mt-6 text-center text-sm text-ink-2">{footer}</div>}
        </div>
        <p className="text-xs text-ink-3">© 2026 MESH · Prototype environment</p>
      </div>

      <aside className="gradient-hero relative hidden overflow-hidden border-l border-line lg:block">
        <div className="dot-grid absolute inset-0 opacity-40" />
        <div className="relative flex h-full flex-col justify-center px-14">
          <div className="float-slow max-w-md rounded-3xl border border-white bg-white/85 p-7 shadow-pop backdrop-blur">
            <span className="flex size-12 items-center justify-center rounded-2xl gradient-violet text-white"><ShieldCheck className="size-6" /></span>
            <p className="mt-5 font-display text-2xl font-bold leading-snug text-ink">Verified organizations, verified people.</p>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
              Owners prove they control their domain. Employees confirm their identity, and a person on your team reviews each ID before anyone is activated.
            </p>
            <ul className="mt-5 space-y-2.5 text-sm text-ink-2">
              {["Domain ownership check", "Human-reviewed ID verification", "Role-based access from day one"].map((t) => (
                <li key={t} className="flex items-center gap-2.5"><span className="flex size-5 items-center justify-center rounded-full bg-tint-mint text-[#008068]">✓</span>{t}</li>
              ))}
            </ul>
          </div>
          {simulated && <div className="float-slower ml-24 mt-6 max-w-[260px] rounded-2xl border border-white bg-white/85 p-4 shadow-pop backdrop-blur">
            <p className="text-xs font-medium text-ink-2">Onboarding today</p>
            <p className="mt-1 font-display text-3xl font-bold">3 <span className="text-sm font-medium text-ink-3">pending reviews</span></p>
          </div>}
        </div>
      </aside>
    </div>
  );
}
