import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { safeRedirect } from "@/lib/messages";
import { routeTree } from "@/routeTree.gen";

type Reply = { status: number; body?: unknown };
type Handler = (request: Request) => Reply | undefined;

const ME = {
  account: { id: 1, display_name: "Cô Lan" },
  school: { name: "THCS Mẫu", subdomain: "a" },
  role_assignments: [],
  capabilities: [],
};

/** The app at `path` with the API answered by `handler` (school and csrf answered for it). */
async function renderApp(path: string, handler: Handler) {
  const calls: Request[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo, init?: RequestInit) => {
    const request =
      input instanceof Request ? input : new Request(new URL(String(input), location.origin), init);
    calls.push(request);
    const { pathname } = new URL(request.url);
    let reply = handler(request);
    if (!reply && pathname === "/api/auth/school/") reply = { status: 200, body: ME.school };
    if (!reply && pathname === "/api/auth/csrf/") {
      document.cookie = "csrftoken=t0ken";
      reply = { status: 204 };
    }
    reply ??= { status: 404 };
    // As DRF answers: a refusal carries `detail`; 204 has no body and no JSON header.
    const body = reply.body ?? (reply.status >= 400 ? { detail: "refused" } : undefined);
    return body === undefined
      ? new Response(null, { status: reply.status })
      : new Response(JSON.stringify(body), {
          status: reply.status,
          headers: { "Content-Type": "application/json" },
        });
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createRouter({ routeTree, history, context: { queryClient } });
  await router.load();
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { calls, history };
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

test("a signed-out visit goes to the login screen, which names the School", async () => {
  const { history } = await renderApp("/gradebook", (r) =>
    r.url.endsWith("/api/auth/me/") ? { status: 403 } : undefined,
  );
  expect(await screen.findByRole("heading", { name: "THCS Mẫu" })).toBeInTheDocument();
  expect(history.location.pathname).toBe("/login");
  expect(history.location.search).toContain("redirect=%2Fgradebook");
});

test("a wrong password shows one message; the right one signs in with CSRF", async () => {
  let attempts = 0;
  const { calls, history } = await renderApp("/login?redirect=%2Fgradebook", (r) => {
    if (r.url.endsWith("/api/auth/login/")) {
      attempts += 1;
      return attempts === 1
        ? { status: 400, body: { non_field_errors: ["Invalid credentials."] } }
        : { status: 200, body: ME };
    }
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
  });
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "sai");
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Sai số điện thoại, email hoặc mật khẩu.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Đăng nhập" }));
  expect(await screen.findByText("Cô Lan")).toBeInTheDocument();
  expect(history.location.pathname).toBe("/gradebook");
  const login = calls.find((c) => c.url.endsWith("/api/auth/login/"));
  expect(login?.headers.get("X-CSRFToken")).toBe("t0ken");
});

test("signing out clears the session and returns to the login screen", async () => {
  let signedIn = true;
  const { history } = await renderApp("/", (r) => {
    if (r.url.endsWith("/api/auth/me/"))
      return signedIn ? { status: 200, body: ME } : { status: 403 };
    if (r.url.endsWith("/api/auth/logout/")) {
      signedIn = false;
      return { status: 204 };
    }
  });
  fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
  await waitFor(() => expect(history.location.pathname).toBe("/login"));
});

test("activation reports a weak password under its field and a bad code once", async () => {
  let attempts = 0;
  await renderApp("/activate", (r) => {
    if (!r.url.endsWith("/api/auth/activate/")) return undefined;
    attempts += 1;
    return attempts === 1
      ? { status: 400, body: { password: ["This password is too short."] } }
      : { status: 400, body: { non_field_errors: ["Invalid or expired invitation."] } };
  });
  await screen.findByRole("heading", { name: "THCS Mẫu" });
  fill("Mã mời", "ABCDE-FGHJK");
  fill("Số điện thoại hoặc email", "0912000111");
  fill("Mật khẩu", "1");
  fireEvent.click(screen.getByRole("button", { name: "Kích hoạt và đăng nhập" }));
  expect(await screen.findByText(/Mật khẩu quá ngắn/)).toBeInTheDocument();
  expect(screen.getByLabelText("Mật khẩu")).toHaveAttribute("aria-invalid", "true");
  fireEvent.click(screen.getByRole("button", { name: "Kích hoạt và đăng nhập" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Mã mời không đúng hoặc đã hết hạn.");
});

test("redirects stay on this site", () => {
  expect(safeRedirect("/gradebook?x=1")).toBe("/gradebook?x=1");
  expect(safeRedirect("//evil.example/x")).toBeUndefined();
  expect(safeRedirect("https://evil.example")).toBeUndefined();
});
