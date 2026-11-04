import type * as React from "react";
import { cn } from "@/lib/utils";

/** A native `<select>`: DESIGN.md, Dense components (up to about seven options). Same box as Input. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2 py-1 text-base shadow-xs outline-none md:text-sm dark:bg-input/30",
        "focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
        "aria-invalid:border-destructive aria-invalid:bg-[var(--color-error-wash)]",
        "disabled:cursor-not-allowed disabled:bg-secondary disabled:text-ink-3",
        className,
      )}
      {...props}
    />
  );
}

export { NativeSelect };
