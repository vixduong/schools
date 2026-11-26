import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { makeApp } from "@/router";

export type Reply = { status: number; body?: unknown };
export type Handler = (request: Request) => Reply | undefined | Promise<Reply | undefined>;

export const ME = {
  account: { id: 1, display_name: "Cô Lan" },
  school: { name: "THCS Mẫu", subdomain: "a" },
  role_assignments: [],
  capabilities: [],
};

/** A row's averages as a semester 1 gradebook sends them while its end-term column is still
 * empty, for fixtures that do not test them. */
export const NO_AVERAGES = {
  semester: {
    value: null,
    result: null,
    state: "missing",
    missing: [{ kind: "end_term", index: 1 }],
    carried: false,
    reason: null,
  },
  year: null,
};

/** `detail` with `NO_AVERAGES` on every row that states none (the API always sends them). */
export function withAverages(detail: Record<string, unknown>) {
  const students = detail.students as Record<string, unknown>[];
  return { ...detail, students: students.map((s) => ({ averages: NO_AVERAGES, ...s })) };
}

/** The app at `path` with the API answered by `handler` (school and csrf answered for it). */
export async function renderApp(path: string, handler: Handler) {
  const calls: Request[] = [];
  vi.stubGlobal("fetch", async (input: RequestInfo, init?: RequestInit) => {
    const request =
      input instanceof Request ? input : new Request(new URL(String(input), location.origin), init);
    calls.push(request);
    const { pathname } = new URL(request.url);
    let reply = await handler(request);
    if (!reply && pathname === "/api/auth/school/") reply = { status: 200, body: ME.school };
    if (!reply && pathname === "/api/portal/children/") reply = { status: 200, body: [] };
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
  const history = createMemoryHistory({ initialEntries: [path] });
  const { queryClient, router } = makeApp(history);
  await router.load();
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { calls, history, queryClient };
}
