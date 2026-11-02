import { createFileRoute, redirect } from "@tanstack/react-router";
import { meQuery, SignedOut } from "@/api/queries";
import { AppShell } from "@/components/app-shell";

// Every signed-in screen sits in here: `me` is loaded first, and no member means /login.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(meQuery);
    } catch (error) {
      if (error instanceof SignedOut) {
        throw redirect({ to: "/login", search: { redirect: location.href } });
      }
      throw error;
    }
  },
  component: AppShell,
});
