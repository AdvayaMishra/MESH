"use client";
import * as React from "react";
import { Dialog as D } from "radix-ui";
import { X } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  className,
  children,
  title,
  description,
  side,
}: {
  className?: string;
  children: React.ReactNode;
  title: string;
  description?: string;
  /** "right" renders as a slide-over drawer. */
  side?: "right";
}) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-[#172033]/35 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in" />
      <D.Content
        className={cn(
          "fixed z-50 bg-white shadow-pop focus:outline-none",
          side === "right"
            ? "right-0 top-0 h-dvh w-full max-w-xl overflow-y-auto border-l border-line"
            : "left-1/2 top-1/2 max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-3xl border border-line",
          className
        )}
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-6">
          <div>
            <D.Title className="font-display text-lg font-semibold text-ink">{title}</D.Title>
            {description ? (
              <D.Description className="mt-1 text-sm text-ink-2">{description}</D.Description>
            ) : (
              <D.Description className="sr-only">{title}</D.Description>
            )}
          </div>
          <D.Close
            aria-label="Close"
            className="rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-[#eef1fa] hover:text-ink"
          >
            <X className="size-4" />
          </D.Close>
        </div>
        <div className="px-6 pb-6 pt-4">{children}</div>
      </D.Content>
    </D.Portal>
  );
}
