"use client";
import * as React from "react";
import { DropdownMenu as M } from "radix-ui";
import { cn } from "@/lib/utils/cn";

export const Dropdown = M.Root;
export const DropdownTrigger = M.Trigger;

export function DropdownContent({
  className,
  align = "end",
  ...props
}: React.ComponentProps<typeof M.Content>) {
  return (
    <M.Portal>
      <M.Content
        align={align}
        sideOffset={8}
        className={cn(
          "z-[60] min-w-52 rounded-2xl border border-line bg-white p-1.5 shadow-pop data-[state=open]:animate-in data-[state=open]:fade-in",
          className
        )}
        {...props}
      />
    </M.Portal>
  );
}

export function DropdownItem({
  className,
  danger,
  icon,
  children,
  ...props
}: React.ComponentProps<typeof M.Item> & { danger?: boolean; icon?: React.ReactNode }) {
  return (
    <M.Item
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-ink outline-none transition-colors data-[highlighted]:bg-tint-violet [&_svg]:size-4 [&_svg]:text-ink-2",
        danger && "text-[#d6294f] data-[highlighted]:bg-tint-coral [&_svg]:text-[#d6294f]",
        className
      )}
      {...props}
    >
      {icon}
      {children}
    </M.Item>
  );
}

export const DropdownLabel = ({ children }: { children: React.ReactNode }) => (
  <M.Label className="px-2.5 py-1.5 text-xs font-medium text-ink-3">{children}</M.Label>
);
export const DropdownSeparator = () => <M.Separator className="my-1 h-px bg-line" />;
