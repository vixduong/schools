import { Link, Outlet } from "@tanstack/react-router";
import { ModeToggle } from "@/components/mode-toggle";

const navLink =
  "px-1 py-2 underline-offset-4 hover:underline data-[status=active]:font-semibold data-[status=active]:underline";

export function AppShell() {
  return (
    <>
      <header className="sticky top-0 z-[var(--z-sticky-nav)] border-b border-border bg-secondary">
        <div className="container flex min-h-14 items-center gap-6">
          <Link to="/" className="font-serif text-xl font-light no-underline">
            sổ trường
          </Link>
          <nav aria-label="Chính" className="flex flex-1 items-center gap-4">
            <Link to="/" className={navLink}>
              Hôm nay
            </Link>
            <Link to="/dang-nhap" className={navLink}>
              Đăng nhập
            </Link>
          </nav>
          <ModeToggle />
        </div>
      </header>
      <main className="container py-10">
        <Outlet />
      </main>
    </>
  );
}
