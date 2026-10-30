"use client";
import { Switch as S } from "radix-ui";
import { cn } from "@/lib/utils/cn";

export function Switch({ className, ...props }: React.ComponentProps<typeof S.Root>) {
  return (
    <S.Root
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full bg-[#d6dcee] transition-colors data-[state=checked]:bg-violet",
        className
      )}
      {...props}
    >
      <S.Thumb className="block size-5 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
    </S.Root>
  );
}
