import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Pin = "open" | "waiting" | "locked" | "alert";

const PIN_COLOUR: Record<Pin, string> = {
  open: "var(--color-pin-open)",
  waiting: "var(--color-pin-waiting)",
  locked: "var(--color-pin-locked)",
  alert: "var(--color-pin-alert)",
};

/** A record with a lifecycle as a pinned ticket (DESIGN.md, brand layer): ticket stock with a
 * 1.5px ink edge, a hatched offset, a pin on the top edge, and the state word in the display
 * face. Not for rows of a table. */
export function Ticket({
  pin,
  state,
  reference,
  children,
  className,
}: {
  pin: Pin;
  state: string;
  reference?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <article
      className={cn(
        "relative isolate mr-1.5 mb-1.5 grid gap-1 px-4 pt-5 pb-4",
        "before:absolute before:inset-0 before:-z-10 before:translate-x-[5px] before:translate-y-[5px] before:rounded-[var(--radius-ticket)] before:bg-[image:var(--hatch)] before:content-['']",
        "after:absolute after:inset-0 after:-z-10 after:rounded-[var(--radius-ticket)] after:border-[1.5px] after:border-foreground after:bg-card after:content-['']",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="absolute -top-[7px] left-1/2 size-3.5 -translate-x-1/2 rounded-full border border-foreground shadow-[inset_-2px_-3px_0_color-mix(in_oklab,var(--color-ink)_25%,transparent)]"
        style={{ background: PIN_COLOUR[pin] }}
      />
      {reference && <p className="text-xs text-ink-3">{reference}</p>}
      <p className="font-serif text-xl font-light leading-tight">{state}</p>
      {children}
    </article>
  );
}
