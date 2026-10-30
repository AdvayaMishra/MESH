"use client";
import { useAdministration } from "@/stores/admin-store";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { PageHeader } from "@/components/features/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge, SimulatedTag } from "@/components/ui/badge";
import { Field, Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useDataset } from "@/lib/api";
import { useWorkspace } from "@/stores/workspace-store";
import { useUI } from "@/stores/ui-store";

export default function OrganizationPage() {
  const { org } = useDataset();
  const saveOrganization = useAdministration((s) => s.saveOrganization);
  const { repos, setRepositoryAuthorization } = useWorkspace();
  const role = useUI((s) => s.role);
  return (
    <div className="space-y-6">
      <PageHeader title="Organization settings" description="Identity, domain and repository authorizations." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card><CardHeader title="Organization" /><CardBody>
          <form key={org.name + org.domain} className="space-y-4" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); const result = saveOrganization(String(f.get("name")), String(f.get("domain"))); if (result.ok) toast.success("Demo identity saved; domain is not verified"); else toast.error(result.error); }}>
            <Field label="Name" htmlFor="oname"><Input id="oname" name="name" defaultValue={org.name} readOnly={role !== "owner"} required minLength={2} maxLength={100} /></Field>
            <Field label="Website" htmlFor="osite"><Input id="osite" name="domain" defaultValue={org.domain} readOnly={role !== "owner"} required /></Field>
            <div className="flex items-center justify-between rounded-xl bg-canvas px-4 py-3 text-sm"><span>Domain verification</span><SimulatedTag label="Not verified by this demo" /></div>
            <p className="text-xs text-ink-3">Edits persist for this demo session. DNS verification and production changes require the backend.</p>
            {role === "owner" && <Button type="submit" variant="gradient">Save organization</Button>}
          </form>
        </CardBody></Card>
        <Card><CardHeader title="Repository scan authorization" subtitle="Demo authorization controls simulated scans; only the owner can change it" /><CardBody>
          <ul className="divide-y divide-line">{repos.map((r) => (
            <li key={r.name} className="flex items-center gap-3 py-3"><span className="min-w-0 flex-1 truncate font-mono text-[13px] font-medium">{r.name}</span><Badge tone={r.authorized ? "mint" : "coral"} dot>{r.authorized ? "Authorized" : "Revoked"}</Badge>
              <Switch checked={r.authorized} disabled={role !== "owner"} onCheckedChange={(v) => { const result = setRepositoryAuthorization(r.name, v); if (result.ok) toast(v ? "Demo authorization enabled" : "Demo authorization revoked"); else toast.error(result.error); }} aria-label={`Authorize scanning of ${r.name}`} /></li>
          ))}</ul>
        </CardBody></Card>
      </div>
    </div>
  );
}
