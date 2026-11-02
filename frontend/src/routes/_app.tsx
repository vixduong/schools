import { createFileRoute, redirect } from "@tanstack/react-router";
import { meQuery, SignedOut } from "@/api/queries";
import { AppShell } from "@/components/app-shell";

// Every signed-in screen sits in here: `me` is loaded first, and no member means /login.
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    try {
      // Cached `me` shows at once and is checked again in the background; a session that ended
      // meanwhile sends the person to /login (makeApp's query cache).
      await context.queryClient.ensureQueryData({ ...meQuery, revalidateIfStale: true });
    } catch (error) {
      if (error instanceof SignedOut) {
        throw redirect({ to: "/login", search: { redirect: location.href } });
      }
      throw error;
    }
  },
  component: AppShell,
});
