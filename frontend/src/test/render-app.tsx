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

/** `detail` with averages on every row that states none (the API always sends them), as a draft
 * semester 1 book sends them: `missing` naming the row's empty columns, else provisional. */
export function withAverages(detail: Record<string, unknown>) {
  const columns = detail.columns as { id: number; kind: string; index: number }[];
  const students = detail.students as { cells?: { column: number }[] }[];
  const commentOnly = detail.assessment === "comment_only";
  return {
    ...detail,
    students: students.map((s) => {
      const filled = new Set(s.cells?.map((c) => c.column));
      const missing = columns
        .filter((c) => !filled.has(c.id))
        .map(({ kind, index }) => ({ kind, index }));
      const done = missing.length === 0;
      const semester = {
        value: done && !commentOnly ? 7 : null,
        result: done && commentOnly ? "pass" : null,
        state: done ? "provisional" : "missing",
        missing,
        carried: false,
        reason: null,
      };
      return { averages: { semester, year: null }, ...s };
    }),
  };
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
