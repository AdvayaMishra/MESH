"use client";
import * as React from "react";
import { Tooltip as T } from "radix-ui";

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return <T.Provider delayDuration={150}>{children}</T.Provider>;
}

export function Tip({
  label,
  children,
  side = "top",
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={8}
          className="z-[70] max-w-xs rounded-lg bg-ink px-2.5 py-1.5 text-xs font-medium text-white shadow-pop"
        >
          {label}
          <T.Arrow className="fill-ink" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
