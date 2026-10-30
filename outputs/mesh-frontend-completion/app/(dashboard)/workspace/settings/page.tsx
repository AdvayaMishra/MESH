"use client";
import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { roleLabels, sections } from "@/lib/nav";
import { ALL_ROLES, canAccess } from "@/lib/permissions";
import { useUI } from "@/stores/ui-store";
import { useTenant } from "@/stores/tenant-store";
import { usePreferences, preferenceKey } from "@/stores/preferences-store";
import { useDataset } from "@/lib/api";

function Row({ title, desc, defaultOn }: { title: string; desc: string; defaultOn?: boolean }) {
  const org = useTenant((s) => s.orgId);
  const role = useUI((s) => s.role);
  const saved = usePreferences((s) => s.preferences[preferenceKey(org, role)]?.[title]);
  const setPreference = usePreferences((s) => s.setPreference);
  const on = saved ?? !!defaultOn;
  const setOn = (value: boolean) => setPreference(org, role, title, value);
  return <div className="flex items-center gap-4 py-3.5"><div className="flex-1"><p className="text-sm font-medium">{title}</p><p className="text-xs text-ink-2">{desc}</p></div><Switch checked={on} onCheckedChange={(v) => { setOn(v); toast(`${title} ${v ? "on" : "off"}`); }} aria-label={title} /></div>;
}

export default function SettingsPage() {
  const { currentUser } = useDataset();
  const role = useUI((s) => s.role);
  const org = useTenant((s) => s.orgId);
  const fileInput = React.useRef<HTMLInputElement>(null);
  const savePhoto = usePreferences((s) => s.savePhoto);
  const saveProfile = usePreferences((s) => s.saveProfile);
  return (
    <div>
      <PageHeader title="Settings" description="Demo profile and preferences persist while navigating this session. Security and email settings do not configure external services." />
      <Tabs defaultValue="profile">
        <TabsList>{["profile", "security", "notifications", "roles"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t === "roles" ? "Role & access" : t}</TabsTrigger>)}</TabsList>
        <TabsContent value="profile"><Card><CardBody className="max-w-xl space-y-4">
          <div className="flex items-center gap-4"><Avatar src={currentUser.photo} name={currentUser.name} size={64} /><input type="file" ref={fileInput} accept="image/png,image/jpeg,image/webp" aria-label="Upload profile photo" className="sr-only" onChange={async (e) => {
            const file = e.target.files?.[0]; e.target.value = ""; if (!file) return;
            if (!/^(image\/(png|jpeg|webp))$/.test(file.type) || file.size > 2 * 1024 * 1024) { toast.error("Choose a PNG, JPEG or WebP image up to 2 MB."); return; }
            try { const bitmap = await createImageBitmap(file); const valid = bitmap.width <= 4096 && bitmap.height <= 4096; bitmap.close(); if (!valid) throw new Error("Image dimensions must be at most 4096 pixels.");
              const reader = new FileReader(); reader.onload = () => { try { savePhoto(org, role, String(reader.result), currentUser.id); toast.success("Demo profile photo saved for this session"); } catch { toast.error("Could not save this image."); } }; reader.onerror = () => toast.error("Could not read this image."); reader.readAsDataURL(file);
            } catch (error) { toast.error(error instanceof Error ? error.message : "Could not decode this image."); }
          }} /><Button variant="secondary" onClick={() => fileInput.current?.click()}>Change photo</Button>{currentUser.photo && <Button variant="ghost" onClick={() => savePhoto(org, role, "", currentUser.id)}>Remove photo</Button>}</div>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); const form = new FormData(e.currentTarget); const error = saveProfile(org, role, { name: String(form.get("name")), email: String(form.get("email")), role: String(form.get("title")) }); if (error) toast.error(error); else toast.success("Demo profile saved for this session"); }}>
            <Field label="Full name" htmlFor="n"><Input name="name" required maxLength={100} id="n" defaultValue={currentUser.name} /></Field>
            <Field label="Email" htmlFor="e"><Input name="email" required maxLength={254} id="e" type="email" defaultValue={currentUser.email} /></Field>
            <Field label="Title" htmlFor="t"><Input name="title" required maxLength={100} id="t" defaultValue={currentUser.role} /></Field>
            <Button type="submit" variant="gradient">Save profile</Button>
          </form></CardBody></Card></TabsContent>
        <TabsContent value="security"><Card><CardHeader title="Security preferences" /><CardBody className="divide-y divide-line">
          <Row title="Two-factor authentication" desc="Demo preference. A live authentication provider must enroll and enforce a factor." defaultOn />
          <Row title="Alert me about new device sign-ins" desc="Demo preference for future provider email delivery." defaultOn />
          <Row title="Auto sign-out after 30 minutes idle" desc="Protects shared machines." />
          <div className="pt-4"><Button variant="secondary" asChild><Link href="/reset-password">Change password</Link></Button></div>
        </CardBody></Card></TabsContent>
        <TabsContent value="notifications"><Card><CardHeader title="Notification preferences" /><CardBody className="divide-y divide-line">
          <Row title="Approval requests" desc="When something needs your decision." defaultOn />
          <Row title="Security incidents" desc="Critical and high severity only." defaultOn />
          <Row title="Weekly summary email" desc="Every Monday at 9:00." />
          <Row title="Product updates" desc="New MESH features." />
        </CardBody></Card></TabsContent>
        <TabsContent value="roles"><Card><CardHeader title="Role-based access" subtitle={`You are previewing as ${roleLabels[role]}`} /><CardBody className="space-y-3">
          {ALL_ROLES.map((r) => <div key={r} className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3.5"><span className="w-40 text-sm font-semibold">{roleLabels[r]}</span><span className="flex flex-1 flex-wrap gap-1.5">{sections.filter((s) => s.id !== "workspace" && s.items.some((i) => canAccess(r, i.href))).map((s) => <Badge key={s.id} tone="violet">{s.id}</Badge>)}</span>{r === role && <Badge tone="mint" dot>Current</Badge>}</div>)}
        </CardBody></Card></TabsContent>
      </Tabs>
    </div>
  );
}
