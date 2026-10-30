import * as React from "react";
import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98] select-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-violet text-white shadow-[0_6px_16px_-6px_rgba(99,91,255,0.7)] hover:bg-indigo hover:shadow-[0_8px_20px_-6px_rgba(79,70,229,0.8)]",
        gradient:
          "gradient-violet text-white shadow-[0_8px_20px_-8px_rgba(99,91,255,0.8)] hover:brightness-110",
        secondary: "bg-white text-ink border border-line-strong hover:bg-tint-violet hover:border-violet/30",
        soft: "bg-tint-violet text-indigo hover:bg-[#e6e2ff]",
        ghost: "text-ink-2 hover:bg-[#eef1fa] hover:text-ink",
        danger: "bg-coral text-white hover:bg-[#f0527a] shadow-[0_6px_16px_-6px_rgba(255,107,138,0.7)]",
        outlineDanger: "border border-coral/40 text-[#d6294f] bg-white hover:bg-tint-coral",
        success: "bg-mint text-[#04332b] hover:brightness-95 shadow-[0_6px_16px_-6px_rgba(0,201,167,0.7)]",
        dark: "bg-ink text-white hover:bg-[#232f4a]",
      },
      size: {
        sm: "h-8 px-3 text-[13px] rounded-lg",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-[15px] rounded-2xl",
        icon: "size-9 rounded-xl",
        iconSm: "size-8 rounded-lg",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot.Root : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  }
);
Button.displayName = "Button";
export { buttonVariants };
