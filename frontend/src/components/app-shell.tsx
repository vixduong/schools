import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, Outlet, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/api/client";
import { meQuery } from "@/api/queries";
import { ModeToggle } from "@/components/mode-toggle";
import { Button } from "@/components/ui/button";
import { reach } from "@/lib/capabilities";

const navLink =
  "px-1 py-2 underline-offset-4 hover:underline data-[status=active]:font-semibold data-[status=active]:underline";

export function AppShell() {
  const { data: me } = useSuspenseQuery(meQuery);
  const queryClient = useQueryClient();
  const router = useRouter();

  const [signOutFailed, setSignOutFailed] = useState(false);

  // Only a confirmed sign-out leaves the screen: on a shared computer a failed one must not look
  // like success while the session is still live.
  async function signOut() {
    const { response } = await api.POST("/api/auth/logout/").catch(() => ({ response: null }));
    if (!response?.ok) {
      setSignOutFailed(true);
      return;
    }
    queryClient.clear();
    router.history.push("/login");
  }

  return (
    <>
      <header className="sticky top-0 z-[var(--z-sticky-nav)] border-b border-border bg-secondary">
        <div className="container flex min-h-14 flex-wrap items-center gap-x-6 gap-y-2 py-2">
          <Link to="/" className="font-serif text-xl font-light no-underline">
            {me.school.name}
          </Link>
          <nav aria-label="Chính" className="flex flex-1 items-center gap-4">
            <Link to="/" className={navLink}>
              Hôm nay
            </Link>
            <Link to="/gradebook" className={navLink}>
              Sổ điểm
            </Link>
            {reach(me, "school.configure") && (
              <Link to="/timetable" className={navLink}>
                Thời khóa biểu
              </Link>
            )}
          </nav>
          <span className="text-sm">{me.account.display_name}</span>
          <ModeToggle />
          <Button variant="quiet" onClick={signOut}>
            Đăng xuất
          </Button>
          {signOutFailed && (
            <p role="alert" className="w-full text-sm text-destructive">
              Chưa đăng xuất được. Kiểm tra mạng rồi bấm Đăng xuất lại.
            </p>
          )}
        </div>
      </header>
      <main className="container py-10">
        <Outlet />
      </main>
    </>
  );
}
