import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

// Variants follow DESIGN.md, Controls: 36px high, one filled primary per screen.
const buttonVariants = cva(
  "inline-flex h-9 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold whitespace-nowrap transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary:
          "border-[1.5px] border-foreground bg-transparent text-foreground hover:bg-secondary",
        quiet: "px-1 underline underline-offset-4 hover:bg-secondary",
        // borderless grid control (calendar days, icon buttons): DESIGN.md, Dense components
        ghost: "px-0 font-normal hover:bg-secondary",
        destructive:
          "border-[1.5px] border-destructive bg-transparent text-destructive hover:bg-destructive/10",
      },
      size: {
        default: "",
        icon: "size-9 px-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
