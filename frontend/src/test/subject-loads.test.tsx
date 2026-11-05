import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, type Reply, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const ADMIN = {
  ...ME,
  capabilities: [{ action: "school.configure", scopes: [{ kind: "school", access: "write" }] }],
};

function loadsApi(
  patches: Request[],
  patch: () => Reply = () => ({ status: 200, body: {} }),
  posts: Request[] = [],
  loads: Record<string, unknown>[] = [
    { id: 9, school_year: 1, grade: 3, subject: 2, periods_per_year: 70 },
  ],
) {
  return (r: Request) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ADMIN };
    if (pathname === "/api/setup/school-years/")
      return {
        status: 200,
        body: [{ id: 1, name: "2026-2027", starts_on: "2000-01-01", ends_on: "2099-12-31" }],
      };
    if (pathname === "/api/setup/grades/")
      return { status: 200, body: [{ id: 3, level: 1, number: 7 }] };
    if (pathname === "/api/setup/subjects/")
      return {
        status: 200,
        body: [
          { id: 2, name: "Toán", code: "MATH", is_active: true },
          { id: 4, name: "Văn", code: "LIT", is_active: true },
        ],
      };
    if (pathname === "/api/setup/subject-loads/" && r.method === "POST") {
      posts.push(r.clone());
      return { status: 201, body: {} };
    }
    if (pathname === "/api/setup/subject-loads/") return { status: 200, body: loads };
    if (pathname === "/api/setup/subject-loads/9/" && r.method === "PATCH") {
      patches.push(r.clone());
      return patch();
    }
  };
}

test("a Grade's table shows each subject's periods and saves a change to the existing load", async () => {
  const patches: Request[] = [];
  await renderApp("/setup/subject-loads", loadsApi(patches));
  const toan = (await screen.findByRole("textbox", { name: "Toán" })) as HTMLInputElement;
  expect(toan).toHaveValue("70");
  expect(screen.getByRole("textbox", { name: "Văn" })).toHaveValue("");
  const save = screen.getByRole("button", { name: "Lưu số tiết Toán, khối 7" });
  expect(save).toBeDisabled();
  fireEvent.change(toan, { target: { value: "105" } });
  fireEvent.click(save);
  await waitFor(() => expect(patches).toHaveLength(1));
  expect(await patches[0]?.json()).toEqual({ periods_per_year: 105 });
});

test("a load a gradebook already uses says so instead of saving", async () => {
  await renderApp(
    "/setup/subject-loads",
    loadsApi([], () => ({
      status: 400,
      body: { constraint: ["subjectload_frozen_by_gradebooks"] },
    })),
  );
  const toan = await screen.findByRole("textbox", { name: "Toán" });
  fireEvent.change(toan, { target: { value: "35" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu số tiết Toán, khối 7" }));
  const row = toan.closest("tr") as HTMLElement;
  expect(await within(row).findByRole("alert")).toHaveTextContent("Đã có sổ điểm dùng số tiết này");
});

test("the board reads the loads without a way to change them", async () => {
  await renderApp("/setup/subject-loads", (r) => {
    if (r.url.endsWith("/api/auth/me/"))
      return {
        status: 200,
        body: {
          ...ME,
          capabilities: [
            { action: "school.configure", scopes: [{ kind: "school", access: "read" }] },
          ],
        },
      };
    return loadsApi([])(r);
  });
  expect(await screen.findByRole("textbox", { name: "Toán" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: /Lưu số tiết/ })).not.toBeInTheDocument();
});

test("a subject with no load yet gets one created, not patched", async () => {
  const posts: Request[] = [];
  const patches: Request[] = [];
  await renderApp("/setup/subject-loads", loadsApi(patches, undefined, posts));
  const van = await screen.findByRole("textbox", { name: "Văn" });
  fireEvent.change(van, { target: { value: "40" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu số tiết Văn, khối 7" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(await posts[0]?.json()).toEqual({
    school_year: 1,
    grade: 3,
    subject: 4,
    periods_per_year: 40,
  });
  expect(patches).toHaveLength(0);
});

test("a row follows the server after a refetch until the person edits it", async () => {
  const loads = [{ id: 9, school_year: 1, grade: 3, subject: 2, periods_per_year: 70 }];
  const { queryClient } = await renderApp(
    "/setup/subject-loads",
    loadsApi([], undefined, [], loads),
  );
  const toan = await screen.findByRole("textbox", { name: "Toán" });
  expect(toan).toHaveValue("70");
  // Another admin changes it: an untouched row shows the new number.
  loads[0] = { ...loads[0], periods_per_year: 105 } as (typeof loads)[number];
  await queryClient.invalidateQueries({ queryKey: ["setup", "subject-loads"] });
  await waitFor(() => expect(toan).toHaveValue("105"));
  // A row being edited keeps what was typed.
  fireEvent.change(toan, { target: { value: "35" } });
  loads[0] = { ...loads[0], periods_per_year: 140 } as (typeof loads)[number];
  await queryClient.invalidateQueries({ queryKey: ["setup", "subject-loads"] });
  await waitFor(() => expect(queryClient.isFetching()).toBe(0));
  expect(toan).toHaveValue("35");
});
