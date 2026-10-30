"use client";
import * as React from "react";
import { Dialog, DialogContent, DialogClose } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "primary",
  requireNote,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  tone?: "primary" | "danger" | "success";
  /** When set, a reviewer note is required before confirming. */
  requireNote?: string;
  onConfirm: (note: string) => void | boolean | Promise<void | boolean>;
  children?: React.ReactNode;
}) {
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState("");
  const [note, setNote] = React.useState("");
  const change = (o: boolean) => {
    if (pending) return;
    if (!o) { setNote(""); setError(""); }
    onOpenChange(o);
  };
  const blocked = !!requireNote && note.trim().length < 3;
  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title={title} description={description}>
        {children}
        {requireNote && (
          <div className="mt-2 space-y-1.5">
            <label className="text-[13px] font-medium text-ink" htmlFor="confirm-note">
              {requireNote}
            </label>
            <Textarea id="confirm-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a short note for the audit log" />
          </div>
        )}
        {error && <p role="alert" className="mt-3 text-sm text-coral">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="secondary" disabled={pending}>Cancel</Button>
          </DialogClose>
          <Button
            variant={tone === "danger" ? "danger" : tone === "success" ? "success" : "primary"}
            disabled={blocked || pending}
            onClick={async () => {
              setPending(true); setError("");
              try { const result = await onConfirm(note); if (result !== false) { setNote(""); onOpenChange(false); } } catch (error) { setError(error instanceof Error ? error.message : "The operation failed. Please try again."); } finally { setPending(false); }
            }}
          >
            {pending ? "Saving…" : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
