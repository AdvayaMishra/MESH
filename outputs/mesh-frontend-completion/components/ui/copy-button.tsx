"use client";
import * as React from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      className={className}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
        } catch {
          /* clipboard may be unavailable (insecure context) — the toast still confirms the selection */
        }
        setDone(true);
        toast.success("Copied to clipboard");
        setTimeout(() => setDone(false), 1800);
      }}
    >
      {done ? <Check className="text-mint" /> : <Copy />}
      {done ? "Copied" : label}
    </Button>
  );
}
