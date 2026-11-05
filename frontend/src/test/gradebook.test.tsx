import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, type Reply, renderApp } from "./render-app";

// Role queries walk a whole grid in jsdom, which is slow.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  vi.unstubAllGlobals();
});

const COLUMNS = [
  { id: 1, kind: "regular", index: 1, released_at: null },
  { id: 2, kind: "regular", index: 2, released_at: null },
  { id: 3, kind: "mid_term", index: 1, released_at: null },
  { id: 4, kind: "end_term", index: 1, released_at: null },
];

function DETAIL(over: Record<string, unknown> = {}) {
  return {
    id: 7,
    school_year: 1,
    term: 1,
    term_name: "HK I",
    subject: 2,
    subject_name: "Toán",
    assessment: "scored",
    school_class: 5,
    class_name: "7A",
    status: "draft",
    opened_at: "2026-11-04T08:00:00+07:00",
    profile_source: "Circular 22/2021/TT-BGDĐT",
    can_enter: true,
    columns: COLUMNS,
    students: [
      { id: 11, name: "An", in_class: true, cells: [] },
      {
        id: 12,
        name: "Bảo",
        in_class: true,
        cells: [{ column: 1, entry: 90, value: 6.5, result: null, changed_after_release: false }],
      },
      {
        id: 13,
        name: "Cường",
        in_class: false,
        cells: [{ column: 1, entry: 91, value: 8, result: null, changed_after_release: false }],
      },
    ],
    ...over,
  };
}

/** The gradebook API; the PUTs are kept (cloned) for the test to read, and answered by `put`. */
function gradebookApi(
  puts: Request[],
  put: () => Reply = () => ({ status: 200, body: { cells: [] } }),
  detail: Record<string, unknown> = {},
) {
  return (r: Request) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/7/") return { status: 200, body: DETAIL(detail) };
    if (pathname === "/api/setup/gradebooks/7/cells/" && r.method === "PUT") {
      puts.push(r.clone());
      return put();
    }
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
  };
}

const cell = (name: string) => screen.findByRole("textbox", { name }) as Promise<HTMLInputElement>;

test("keyboard entry: Enter and arrows move between cells, and one save sends only the typed cells", async () => {
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => ({
      status: 200,
      body: {
        cells: [
          { column: 1, student: 11, entry: 100 },
          { column: 2, student: 11, entry: 101 },
        ],
      },
    })),
  );
  const first = await cell("An, TX1");
  first.focus();
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  fireEvent.change(first, { target: { value: "7,5" } });
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
  // Arrow right to TX2; Enter goes down, to Bảo (the left student below has no field).
  fireEvent.keyDown(first, { key: "ArrowRight" });
  const second = await cell("An, TX2");
  expect(second).toHaveFocus();
  fireEvent.change(second, { target: { value: "9" } });
  fireEvent.keyDown(second, { key: "Enter" });
  expect(await cell("Bảo, TX2")).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Bảo, TX2" }), { key: "ArrowUp" });
  expect(second).toHaveFocus();
  expect(screen.getByText("Chưa lưu 2 ô")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(await puts[0]?.json()).toEqual({
    cells: [
      { column: 1, student: 11, value: 7.5, expected: null },
      { column: 2, student: 11, value: 9, expected: null },
    ],
  });
  await waitFor(() => expect(screen.getByText("Đã lưu")).toBeInTheDocument());
});

test("a cell is saved against the entry the client saw, and a typed value equal to the saved one is no change", async () => {
  const puts: Request[] = [];
  await renderApp("/gradebook/7", gradebookApi(puts));
  const bao = await cell("Bảo, TX1");
  expect(bao).toHaveValue("6,5");
  fireEvent.change(bao, { target: { value: "7" } });
  fireEvent.change(bao, { target: { value: "6,5" } });
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  fireEvent.change(bao, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(await puts[0]?.json()).toEqual({
    cells: [{ column: 1, student: 12, value: null, expected: 90 }],
  });
});

test("text that is no score is flagged on its cell and never sent as a clearing", async () => {
  const puts: Request[] = [];
  await renderApp("/gradebook/7", gradebookApi(puts));
  const an = await cell("An, TX1");
  fireEvent.change(an, { target: { value: "abc" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByText("Chưa phải số điểm.")).toBeInTheDocument();
  expect(an).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByText("Lỗi 1 ô")).toBeInTheDocument();
  expect(puts).toHaveLength(0);
});

test("a conflict shows the server's value on its cell, keeps what was typed, and can be kept over", async () => {
  const puts: Request[] = [];
  let answer: Reply = {
    status: 400,
    body: {
      cells: [
        {
          column: 1,
          student: 12,
          code: "conflict",
          current: {
            entry: 95,
            value: 9,
            result: null,
            entered_by_name: "Cô Hoa",
            entered_at: "2026-11-04T15:40:00Z",
          },
        },
      ],
    },
  };
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => answer),
  );
  const bao = await cell("Bảo, TX1");
  const an = await cell("An, TX2");
  fireEvent.change(bao, { target: { value: "8" } });
  fireEvent.change(an, { target: { value: "7" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

  // The cell keeps the typed 8 and shows the other value beside it, in red ink.
  const td = (await screen.findByText("Hiện có: 9")).closest("td") as HTMLElement;
  expect(within(td).getByRole("textbox")).toHaveValue("8");
  expect(within(td).getByText("Người khác vừa lưu ô này.")).toHaveClass("text-destructive");
  expect(bao).toHaveAttribute("aria-invalid", "true");
  expect(bao).toHaveAccessibleDescription(/Người khác vừa lưu ô này/);
  expect(screen.getByText("Lỗi 1 ô")).toBeInTheDocument();
  // Nothing typed is lost: the other cell is still unsaved text.
  expect(an).toHaveValue("7");
  expect(screen.getByText(/Cô Hoa/)).toBeInTheDocument();

  // Keep mine: the next save names the entry just seen, so it can win knowingly.
  fireEvent.click(screen.getByRole("button", { name: "Giữ số của tôi" }));
  answer = { status: 200, body: { cells: [] } };
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(2));
  expect(await puts[1]?.json()).toEqual({
    cells: [
      { column: 1, student: 12, value: 8, expected: 95 },
      { column: 2, student: 11, value: 7, expected: null },
    ],
  });
});

test("a failed save never clears what was typed", async () => {
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => ({ status: 500 })),
  );
  const an = await cell("An, TX1");
  fireEvent.change(an, { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
  expect(an).toHaveValue("8");
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
  // A rule only the database holds is its own message, and keeps the cells too.
  await waitFor(() => expect(screen.getByRole("button", { name: "Lưu" })).toBeEnabled());
});

test("a database refusal of the whole save says the class may have changed and keeps the cells", async () => {
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => ({
      status: 400,
      body: { constraint: ["scoreentry_student_in_class"] },
    })),
  );
  const an = await cell("An, TX1");
  fireEvent.change(an, { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Danh sách lớp có thể đã thay đổi");
  expect(an).toHaveValue("8");
});

test("a student who left is greyed and read only, with the scores they keep", async () => {
  await renderApp("/gradebook/7", gradebookApi([]));
  const row = (await screen.findByRole("rowheader", { name: /Cường/ })).closest(
    "tr",
  ) as HTMLElement;
  expect(row).toHaveClass("text-ink-3");
  expect(within(row).getByText("đã rời lớp")).toBeInTheDocument();
  expect(within(row).queryByRole("textbox")).not.toBeInTheDocument();
  expect(within(row).getByText("8")).toBeInTheDocument();
});

test("a reader without scores.enter sees the grid read only", async () => {
  await renderApp("/gradebook/7", gradebookApi([], undefined, { can_enter: false }));
  await screen.findByRole("rowheader", { name: "An" });
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Lưu" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Công bố cột/ })).not.toBeInTheDocument();
  expect(screen.getByText("Bạn chỉ xem được sổ điểm này.")).toBeInTheDocument();
});

test("releasing a column asks first, and says who still has no score", async () => {
  const posts: Request[] = [];
  let reply: Reply = {
    status: 400,
    body: { column: ["incomplete"], students: [{ id: 11, name: "An" }] },
  };
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/7/columns/1/release/") {
      posts.push(r.clone());
      return reply;
    }
    return gradebookApi([])(r);
  });
  await screen.findByText("Bảo"); // role queries are slow on a big grid: wait for it first
  fireEvent.click(await screen.findByRole("button", { name: "Công bố cột TX1" }));
  const dialog = await screen.findByRole("dialog", { name: "Công bố cột TX1?" });
  expect(posts).toHaveLength(0); // nothing is released by the click that asks
  fireEvent.click(within(dialog).getByRole("button", { name: "Công bố" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Còn 1 học sinh chưa có điểm cột TX1: An.",
  );
  reply = {
    status: 200,
    body: { id: 1, kind: "regular", index: 1, released_at: "2026-11-04T15:40:00Z" },
  };
  fireEvent.click(within(dialog).getByRole("button", { name: "Công bố" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(posts).toHaveLength(2);
});

test("a cell's history opens in a popover, oldest first", async () => {
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/7/history/")
      return {
        status: 200,
        body: [
          {
            id: 1,
            value: 6,
            result: null,
            entered_by_name: "Cô Lan",
            entered_at: "2026-11-03T03:00:00Z",
          },
          {
            id: 90,
            value: 6.5,
            result: null,
            entered_by_name: "Cô Hoa",
            entered_at: "2026-11-04T03:00:00Z",
          },
        ],
      };
    return gradebookApi([])(r);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Lịch sử Bảo, TX1" }));
  await screen.findByText(/Cô Lan/);
  const items = within(await screen.findByRole("list")).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("6");
  expect(items[0]).toHaveTextContent("Cô Lan");
  expect(items[1]).toHaveTextContent("6,5");
  expect(items[1]).toHaveTextContent("Cô Hoa");
});

test("a comment-only subject takes Đạt or Chưa đạt from a select", async () => {
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, undefined, {
      assessment: "comment_only",
      students: [{ id: 11, name: "An", in_class: true, cells: [] }],
    }),
  );
  const select = await screen.findByRole("combobox", { name: "An, TX1" });
  fireEvent.change(select, { target: { value: "fail" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(await puts[0]?.json()).toEqual({
    cells: [{ column: 1, student: 11, value: null, result: "fail", expected: null }],
  });
});

test("the teacher home lists the open gradebooks under Đang nhập", async () => {
  const me = {
    ...ME,
    capabilities: [
      { action: "scores.enter", scopes: [{ kind: "teaching_pair", access: "write" }] },
    ],
  };
  await renderApp("/", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: me };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
    if (pathname === "/api/setup/gradebooks/mine/")
      return {
        status: 200,
        body: [
          {
            subject: 2,
            subject_name: "Toán",
            school_class: 5,
            class_name: "7A",
            terms: [
              { term: 1, term_name: "HK I", gradebook: 7, status: "draft" },
              { term: 2, term_name: "HK II", gradebook: null, status: null },
            ],
          },
        ],
      };
  });
  const open = await screen.findByRole("region", { name: "Đang nhập" });
  expect(await within(open).findByText("Toán · lớp 7A · HK I")).toBeInTheDocument();
  expect(within(open).getByRole("link", { name: "Vào sổ" })).toHaveAttribute(
    "href",
    "/gradebook/7",
  );
  expect(within(open).queryByText(/HK II/)).not.toBeInTheDocument();
  expect(screen.getByText("Chưa có hồ sơ nào đã khoá.")).toBeInTheDocument();
});

test("the picker opens a gradebook for a term that has none and goes to its grid", async () => {
  const opens: Request[] = [];
  const { history } = await renderApp("/gradebook", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/mine/")
      return {
        status: 200,
        body: [
          {
            subject: 2,
            subject_name: "Toán",
            school_class: 5,
            class_name: "7A",
            terms: [
              { term: 1, term_name: "HK I", gradebook: 7, status: "draft" },
              { term: 2, term_name: "HK II", gradebook: null, status: null },
            ],
          },
        ],
      };
    if (pathname === "/api/setup/gradebooks/" && r.method === "POST") {
      opens.push(r.clone());
      return { status: 201, body: DETAIL({ id: 8 }) };
    }
    return gradebookApi([])(r);
  });
  expect(await screen.findByRole("link", { name: /HK I, Toán/ })).toHaveAttribute(
    "href",
    "/gradebook/7",
  );
  fireEvent.click(screen.getByRole("button", { name: /Mở sổ HK II/ }));
  await waitFor(() => expect(opens).toHaveLength(1));
  expect(await opens[0]?.json()).toEqual({ term: 2, subject: 2, school_class: 5 });
  await waitFor(() => expect(history.location.pathname).toBe("/gradebook/8"));
});

test("a term with no subject load says who to ask", async () => {
  await renderApp("/gradebook", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/mine/")
      return {
        status: 200,
        body: [
          {
            subject: 2,
            subject_name: "Toán",
            school_class: 5,
            class_name: "7A",
            terms: [{ term: 1, term_name: "HK I", gradebook: null, status: null }],
          },
        ],
      };
    if (pathname === "/api/setup/gradebooks/" && r.method === "POST")
      return { status: 400, body: { gradebook: ["no_subject_load"] } };
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
  });
  fireEvent.click(await screen.findByRole("button", { name: /Mở sổ HK I/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("chưa nhập số tiết");
});
