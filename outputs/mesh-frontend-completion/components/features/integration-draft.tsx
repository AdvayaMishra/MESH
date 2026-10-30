"use client";
import * as React from "react";
import { toast } from "sonner";
import { useDataset } from "@/lib/api";
import { useTenant } from "@/stores/tenant-store";
import { useDrafts } from "@/stores/drafts-store";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
export function IntegrationDraft({ open, onOpenChange, target, title }: { open: boolean; onOpenChange: (open: boolean) => void; target: string; title: string }) {
  const org = useTenant((s) => s.orgId);
  const { currentUser } = useDataset();
  const { drafts, save } = useDrafts();
  const existing = drafts.filter((d) => d.org === org && d.actor === currentUser.id && d.target === target);
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent title={title} description={`For ${target}. Drafts stay in this demo session; nothing is sent externally.`}>
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); try { save({ org, actor: currentUser.id, target, subject: String(f.get("subject")), body: String(f.get("body")) }); toast.success("Integration draft saved locally"); e.currentTarget.reset(); } catch (error) { toast.error(error instanceof Error ? error.message : "Could not save draft"); } }}>
      <Field label="Subject" htmlFor="draft-subject"><Input id="draft-subject" name="subject" required minLength={3} maxLength={200} defaultValue={title} /></Field>
      <Field label="Message" htmlFor="draft-body"><Textarea id="draft-body" name="body" required minLength={10} maxLength={5000} /></Field>
      <Button type="submit" variant="gradient">Save draft</Button>
    </form>
    <ul className="mt-4 max-h-48 space-y-2 overflow-y-auto">{existing.map((draft) => <li key={draft.id} className="rounded-xl border border-line p-3"><p className="text-sm font-semibold">{draft.subject}</p><p className="whitespace-pre-wrap text-sm text-ink-2">{draft.body}</p><Button size="sm" variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`); toast.success("Draft copied"); } catch { toast.error("Clipboard permission unavailable; select and copy the draft text."); } }}>Copy draft</Button></li>)}</ul>
  </DialogContent></Dialog>;
}
