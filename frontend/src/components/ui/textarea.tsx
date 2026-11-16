import type * as React from "react";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-32 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs outline-none placeholder:text-muted-foreground md:text-sm dark:bg-input/30",
        "focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
        "aria-invalid:border-destructive aria-invalid:bg-[var(--color-error-wash)]",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
