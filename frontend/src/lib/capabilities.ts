import type { Me } from "@/api/client";

/** What the signed-in member may do with an action: "write", "read" (view only), or nothing. */
export function reach(me: Me, action: string): "write" | "read" | undefined {
  const scopes = me.capabilities.find((c) => c.action === action)?.scopes ?? [];
  if (scopes.some((s) => s.access === "write")) return "write";
  return scopes.length ? "read" : undefined;
}
