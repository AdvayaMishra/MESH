"use client";
import * as React from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

const links = [
  { label: "Modules", href: "#modules" },
  { label: "Product", href: "#product" },
  { label: "Intelligence", href: "#intelligence" },
  { label: "Security", href: "#security" },
  { label: "FAQ", href: "#faq" },
];

export function MarketingNav() {
  const [open, setOpen] = React.useState(false);
  const [scrolled, setScrolled] = React.useState(false);
  React.useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={`fixed inset-x-0 top-0 z-50 transition-all ${scrolled ? "border-b border-line bg-white/80 backdrop-blur-lg" : "bg-transparent"}`}>
      <div className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-5 sm:px-8">
        <Link href="/" aria-label="MESH home"><Logo /></Link>
        <nav aria-label="Marketing" className="hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <a key={l.href} href={l.href} className="rounded-lg px-3.5 py-2 text-sm font-medium text-ink-2 transition-colors hover:bg-white hover:text-ink">
              {l.label}
            </a>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <Button variant="ghost" asChild><Link href="/login">Log in</Link></Button>
          <Button variant="gradient" asChild><Link href="/register">Get started</Link></Button>
        </div>
        <button className="flex size-10 items-center justify-center rounded-xl border border-line bg-white md:hidden" onClick={() => setOpen((o) => !o)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <div className="border-t border-line bg-white px-5 pb-5 pt-2 md:hidden">
          {links.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-3 text-[15px] font-medium text-ink-2 hover:bg-canvas">{l.label}</a>
          ))}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Button variant="secondary" asChild><Link href="/login">Log in</Link></Button>
            <Button variant="gradient" asChild><Link href="/register">Get started</Link></Button>
          </div>
        </div>
      )}
    </header>
  );
}

const cols = [
  { title: "Product", items: [["MESH Owner", "/owner"], ["MESH People", "/people"], ["DevTrack", "/devtrack"], ["VADER", "/vader"]] },
  { title: "Company", items: [["About", "#"], ["Careers", "#"], ["Customers", "#"], ["Contact", "#"]] },
  { title: "Resources", items: [["Documentation", "/workspace/help"], ["Security overview", "#security"], ["Status", "#"], ["Changelog", "#"]] },
  { title: "Legal", items: [["Privacy", "#"], ["Terms", "#"], ["Data processing", "#"], ["Responsible disclosure", "#"]] },
];

export function MarketingFooter() {
  return (
    <footer className="border-t border-line bg-white">
      <div className="mx-auto max-w-7xl px-5 py-14 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[1.4fr_2fr]">
          <div>
            <Logo />
            <p className="mt-4 max-w-sm text-sm text-ink-2">
              One workspace for people, projects, operations and security. Built for teams that need to see the whole picture.
            </p>
            <div className="mt-5 inline-flex items-center gap-2 rounded-full bg-tint-mint px-3 py-1.5 text-xs font-medium text-[#008068]">
              <span className="size-2 rounded-full bg-mint" /> Prototype environment · all data is simulated
            </div>
          </div>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            {cols.map((c) => (
              <div key={c.title}>
                <p className="font-display text-sm font-semibold text-ink">{c.title}</p>
                <ul className="mt-3 space-y-2.5">
                  {c.items.map(([label, href]) => (
                    <li key={label}>
                      {href.startsWith("/") ? (
                        <Link href={href} className="text-sm text-ink-2 hover:text-indigo">{label}</Link>
                      ) : (
                        <a href={href} className="text-sm text-ink-2 hover:text-indigo">{label}</a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-line pt-6 text-xs text-ink-3 sm:flex-row sm:items-center">
          <p>© 2026 MESH. All rights reserved.</p>
          <p>Designed in Bengaluru. Shipped everywhere.</p>
        </div>
      </div>
    </footer>
  );
}
