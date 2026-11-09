import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { DRAFT_LIFETIME_MS, draftKey, readDraft } from "@/lib/drafts";
import { ME, type Reply, renderApp } from "./render-app";

// Role queries walk a whole grid in jsdom, which is slow.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
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
    steps: [],
    return_comment: null,
    can: [],
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
  put: () => Reply | Promise<Reply> = () => ({ status: 200, body: { cells: [] } }),
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
  const detail: Record<string, unknown> = {};
  const { calls } = await renderApp(
    "/gradebook/7",
    gradebookApi(
      puts,
      () => {
        // The server now holds the two scores: the refetch after the save brings them back.
        const [an, ...rest] = DETAIL().students;
        detail.students = [
          {
            ...an,
            cells: [
              { column: 1, entry: 100, value: 7.5, result: null, changed_after_release: false },
              { column: 2, entry: 101, value: 9, result: null, changed_after_release: false },
            ],
          },
          ...rest,
        ];
        return {
          status: 200,
          body: {
            cells: [
              { column: 1, student: 11, entry: 100 },
              { column: 2, student: 11, entry: 101 },
            ],
          },
        };
      },
      detail,
    ),
  );
  const first = await cell("An, TX1");
  first.focus();
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  fireEvent.change(first, { target: { value: "7,5" } });
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
  // Arrow right to TX2; Enter goes down to Bảo.
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
  // The saved scores show, also after the refetch the save triggers.
  await waitFor(() =>
    expect(
      calls.filter((c) => new URL(c.url).pathname === "/api/setup/gradebooks/7/"),
    ).toHaveLength(2),
  );
  expect(first).toHaveValue("7,5");
  expect(second).toHaveValue("9");
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

  // The first refused cell takes the focus; the buttons say which cell they are for.
  await waitFor(() => expect(bao).toHaveFocus());
  expect(screen.getByRole("button", { name: "Dùng số đang có, Bảo TX1" })).toBeInTheDocument();

  // Keep mine: the next save names the entry just seen, so it can win knowingly.
  fireEvent.click(screen.getByRole("button", { name: "Giữ số của tôi, Bảo TX1" }));
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
  const items = within(await screen.findByRole("list", { name: "Các lần nhập" })).getAllByRole(
    "listitem",
  );
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

// --- what survives a refetch, a left student, a pending save, leaving the page ---------------

const SOMEONE_ELSE_SAVED_AN = (over: Record<string, unknown> = {}) => ({
  students: [
    {
      id: 11,
      name: "An",
      in_class: true,
      cells: [{ column: 1, entry: 120, value: 9, result: null, changed_after_release: false }],
      ...over,
    },
    ...DETAIL().students.slice(1),
  ],
});

test("an edit keeps the entry it was typed against when the grid is refetched meanwhile", async () => {
  const puts: Request[] = [];
  const detail: Record<string, unknown> = {};
  const { calls, queryClient } = await renderApp(
    "/gradebook/7",
    gradebookApi(puts, undefined, detail),
  );
  const an = await cell("An, TX1");
  fireEvent.change(an, { target: { value: "7" } });
  // Someone else saves An's TX1 (entry 120) and the grid is refetched while the edit is open.
  Object.assign(detail, SOMEONE_ELSE_SAVED_AN());
  const before = calls.length;
  await queryClient.invalidateQueries({ queryKey: ["gradebook", 7] });
  await waitFor(() => expect(calls.length).toBeGreaterThan(before));
  // Typing on moves the text, not the entry the edit was made against: it still conflicts.
  fireEvent.change(await cell("An, TX1"), { target: { value: "7,5" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(await puts[0]?.json()).toEqual({
    cells: [{ column: 1, student: 11, value: 7.5, expected: null }],
  });
});

test("typed text on a student who left is shown read only and can be dropped, which unblocks the save and the release", async () => {
  const puts: Request[] = [];
  const detail: Record<string, unknown> = {};
  await renderApp(
    "/gradebook/7",
    gradebookApi(
      puts,
      () => {
        // The student left the class while the teacher typed; the refetch after the refusal shows it.
        Object.assign(detail, {
          students: [
            { id: 11, name: "An", in_class: false, cells: [] },
            ...DETAIL().students.slice(1),
          ],
        });
        return {
          status: 400,
          body: { cells: [{ column: 1, student: 11, code: "not_enrolled", current: null }] },
        };
      },
      detail,
    ),
  );
  fireEvent.change(await cell("An, TX1"), { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  const drop = await screen.findByRole("button", { name: "Bỏ ô này, An, TX1" });
  const td = drop.closest("td") as HTMLElement;
  expect(within(td).queryByRole("textbox")).not.toBeInTheDocument();
  expect(within(td).getByText("8")).toBeInTheDocument(); // what was typed is not lost silently
  expect(within(td).getByText("Học sinh không còn trong lớp.")).toBeInTheDocument();
  expect(screen.getByText("Lỗi 1 ô")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Công bố cột TX1" })).toBeDisabled();
  fireEvent.click(drop);
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Lưu" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Công bố cột TX1" })).toBeEnabled();
  expect(within(td).queryByText("8")).not.toBeInTheDocument();
});

test("leaving the page with unsaved cells asks first, naming how many", async () => {
  const confirm = vi.fn((_message: string) => false);
  vi.stubGlobal("confirm", confirm);
  const { history } = await renderApp("/gradebook/7", gradebookApi([]));
  // Nothing typed: nothing to ask.
  history.push("/gradebook");
  await waitFor(() => expect(history.location.pathname).toBe("/gradebook"));
  history.push("/gradebook/7");
  await waitFor(() => expect(history.location.pathname).toBe("/gradebook/7"));
  expect(confirm).not.toHaveBeenCalled();

  fireEvent.change(await cell("An, TX1"), { target: { value: "7" } });
  fireEvent.change(await cell("An, TX2"), { target: { value: "8" } });
  history.push("/gradebook");
  await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
  expect(String(confirm.mock.calls[0]?.[0])).toContain("Còn 2 ô chưa lưu");
  expect(history.location.pathname).toBe("/gradebook/7"); // refused: still here, cells kept
  expect(screen.getByText("Chưa lưu 2 ô")).toBeInTheDocument();
  confirm.mockReturnValue(true);
  history.push("/gradebook");
  await waitFor(() => expect(history.location.pathname).toBe("/gradebook"));
});

test("Dùng số đang có drops the typed number and shows the one the server has", async () => {
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => ({
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
    })),
  );
  const bao = await cell("Bảo, TX1");
  fireEvent.change(bao, { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  fireEvent.click(await screen.findByRole("button", { name: "Dùng số đang có, Bảo TX1" }));
  expect(bao).toHaveValue("6,5"); // the grid's own number again, until the refetch brings 9
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  expect(screen.queryByText("Lỗi 1 ô")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Giữ số của tôi/ })).not.toBeInTheDocument();
});

test("cells are read only while a save is pending, and a refusal of text changed since is not pinned on it", async () => {
  let finish!: (reply: Reply) => void;
  const answer = new Promise<Reply>((resolve) => {
    finish = resolve;
  });
  const puts: Request[] = [];
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => answer),
  );
  const an = await cell("An, TX1");
  fireEvent.change(an, { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(an).toHaveAttribute("readonly"));
  expect(screen.getByText("Đang lưu…")).toBeInTheDocument();
  // Text that still gets in (a script, a paste the browser let through) is not what was sent.
  fireEvent.change(an, { target: { value: "9" } });
  finish({
    status: 400,
    body: { cells: [{ column: 1, student: 11, code: "out_of_range", current: null }] },
  });
  await waitFor(() => expect(an).not.toHaveAttribute("readonly"));
  expect(an).toHaveValue("9");
  expect(an).not.toHaveAttribute("aria-invalid");
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
});

test("a comment-only cell is disabled while a save is pending", async () => {
  let finish!: (reply: Reply) => void;
  const answer = new Promise<Reply>((resolve) => {
    finish = resolve;
  });
  await renderApp(
    "/gradebook/7",
    gradebookApi([], () => answer, {
      assessment: "comment_only",
      students: [{ id: 11, name: "An", in_class: true, cells: [] }],
    }),
  );
  const select = await screen.findByRole("combobox", { name: "An, TX1" });
  fireEvent.change(select, { target: { value: "pass" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(select).toBeDisabled());
  finish({ status: 200, body: { cells: [{ column: 1, student: 11, entry: 5 }] } });
  await waitFor(() => expect(select).toBeEnabled());
});

test("a column cannot be released while cells are unsaved", async () => {
  await renderApp("/gradebook/7", gradebookApi([]));
  const release = await screen.findByRole("button", { name: "Công bố cột TX1" });
  expect(release).toBeEnabled();
  fireEvent.change(await cell("An, TX1"), { target: { value: "7" } });
  expect(release).toBeDisabled();
});

test("a 400 that names no cell properly is the generic message, not a cell verdict", async () => {
  await renderApp(
    "/gradebook/7",
    gradebookApi([], () => ({ status: 400, body: { cells: [{ expected: ["required"] }] } })),
  );
  fireEvent.change(await cell("An, TX1"), { target: { value: "8" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Không lưu được điểm");
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
});

test("checking the typed text keeps the server's earlier verdicts on other cells", async () => {
  await renderApp(
    "/gradebook/7",
    gradebookApi([], () => ({
      status: 400,
      body: { cells: [{ column: 2, student: 11, code: "out_of_range", current: null }] },
    })),
  );
  fireEvent.change(await cell("An, TX2"), { target: { value: "11" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByText("Điểm từ 0 đến 10.")).toBeInTheDocument();
  fireEvent.change(await cell("An, TX1"), { target: { value: "abc" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByText("Chưa phải số điểm.")).toBeInTheDocument();
  expect(screen.getByText("Điểm từ 0 đến 10.")).toBeInTheDocument();
  expect(screen.getByText("Lỗi 2 ô")).toBeInTheDocument();
});

test("the release dialog opens clean for the next column after a refusal", async () => {
  await renderApp("/gradebook/7", (r) => {
    if (new URL(r.url).pathname === "/api/setup/gradebooks/7/columns/1/release/")
      return { status: 400, body: { column: ["incomplete"], students: [{ id: 11, name: "An" }] } };
    return gradebookApi([])(r);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Công bố cột TX1" }));
  let dialog = await screen.findByRole("dialog", { name: "Công bố cột TX1?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Công bố" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Còn 1 học sinh");
  fireEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Công bố cột TX2" }));
  dialog = await screen.findByRole("dialog", { name: "Công bố cột TX2?" });
  expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
});

test("the history opens by Alt+H on any keyboard, by Tab for a student who left, and hands the focus back", async () => {
  await renderApp("/gradebook/7", (r) => {
    if (new URL(r.url).pathname === "/api/setup/gradebooks/7/history/")
      return { status: 200, body: [] };
    return gradebookApi([])(r);
  });
  const bao = await cell("Bảo, TX1");
  // A field has Alt+H (the physical H key: a Mac's Option+H types another character).
  expect(screen.getByRole("button", { name: "Lịch sử Bảo, TX1" })).toHaveAttribute(
    "tabindex",
    "-1",
  );
  bao.focus();
  fireEvent.keyDown(bao, { key: "˙", code: "KeyH", altKey: true });
  await screen.findByText("Lịch sử: Bảo, TX1");
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByText("Lịch sử: Bảo, TX1")).not.toBeInTheDocument());
  await waitFor(() => expect(bao).toHaveFocus());
  // A student who left has no field: the button is the way in.
  expect(screen.getByRole("button", { name: "Lịch sử Cường, TX1" })).toHaveAttribute(
    "tabindex",
    "0",
  );
});

test("a reader's history buttons are reachable by Tab", async () => {
  await renderApp("/gradebook/7", gradebookApi([], undefined, { can_enter: false }));
  expect(await screen.findByRole("button", { name: "Lịch sử Bảo, TX1" })).toHaveAttribute(
    "tabindex",
    "0",
  );
});

test("a failed refetch keeps the grid on screen and says nothing about not opening it", async () => {
  let fail = false;
  const { queryClient } = await renderApp("/gradebook/7", (r) => {
    if (fail && new URL(r.url).pathname === "/api/setup/gradebooks/7/") return { status: 500 };
    return gradebookApi([])(r);
  });
  await cell("An, TX1");
  fail = true;
  await queryClient.invalidateQueries({ queryKey: ["gradebook", 7] });
  await waitFor(() => expect(queryClient.getQueryState(["gradebook", 7])?.status).toBe("error"));
  expect(screen.getByRole("textbox", { name: "An, TX1" })).toBeInTheDocument();
  expect(screen.queryByText(/Không mở được sổ điểm/)).not.toBeInTheDocument();
}, 20_000); // the query retries twice before it gives up

// --- the draft kept in the browser ------------------------------------------------------------

const AN_TX1 = "1:11";
const draftOf = (edits: Record<string, { text: string; expected: number | null }>, age = 0) =>
  JSON.stringify({ at: Date.now() - age, edits });

test("typing writes a draft in the browser, and a confirmed save takes the cell out of it", async () => {
  const key = draftKey(ME.account.id, 7);
  await renderApp(
    "/gradebook/7",
    gradebookApi([], () => ({
      status: 200,
      body: { cells: [{ column: 1, student: 11, entry: 100 }] },
    })),
  );
  fireEvent.change(await cell("An, TX1"), { target: { value: "7,5" } });
  fireEvent.change(await cell("Bảo, TX1"), { target: { value: "8" } });
  expect(readDraft(key)).toEqual({
    [AN_TX1]: { text: "7,5", expected: null },
    "1:12": { text: "8", expected: 90 },
  });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  // The server confirmed An's cell only (the mock saw both, answers one): Bảo's stays.
  await waitFor(() => expect(readDraft(key)).toEqual({ "1:12": { text: "8", expected: 90 } }));
  fireEvent.change(await cell("Bảo, TX1"), { target: { value: "6,5" } }); // back to the saved text
  expect(localStorage.getItem(key)).toBeNull(); // nothing left: the key goes
});

test("an earlier draft is offered, restored with the entry it was typed against, and never saved by itself", async () => {
  const key = draftKey(ME.account.id, 7);
  const puts: Request[] = [];
  // Last visit: Bảo's TX1 (entry 90) was changed to 8 and not saved.
  await renderApp("/gradebook/7", gradebookApi([]));
  fireEvent.change(await cell("Bảo, TX1"), { target: { value: "8" } });
  cleanup();
  vi.unstubAllGlobals();
  expect(readDraft(key)).toEqual({ "1:12": { text: "8", expected: 90 } });

  // This visit: someone else has saved Bảo's TX1 meanwhile (entry 95).
  const answer: Reply = {
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
  const detail = {
    students: [
      ...DETAIL().students.slice(0, 1),
      {
        id: 12,
        name: "Bảo",
        in_class: true,
        cells: [{ column: 1, entry: 95, value: 9, result: null, changed_after_release: false }],
      },
      ...DETAIL().students.slice(2),
    ],
  };
  await renderApp(
    "/gradebook/7",
    gradebookApi(puts, () => answer, detail),
  );
  const banner = await screen.findByRole("region", { name: "Bản nháp chưa lưu" });
  expect(banner).toHaveTextContent("Còn 1 ô chưa lưu từ lần trước");
  expect(await cell("Bảo, TX1")).toHaveValue("9"); // offered, not applied
  expect(screen.getByText("Đã lưu")).toBeInTheDocument();
  expect(puts).toHaveLength(0);

  fireEvent.click(within(banner).getByRole("button", { name: "Khôi phục" }));
  expect(screen.queryByRole("region", { name: "Bản nháp chưa lưu" })).not.toBeInTheDocument();
  expect(await cell("Bảo, TX1")).toHaveValue("8");
  expect(screen.getByText("Chưa lưu 1 ô")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  // It still names entry 90, so the server says someone else saved: never a silent overwrite.
  expect(await puts[0]?.json()).toEqual({
    cells: [{ column: 1, student: 12, value: 8, expected: 90 }],
  });
  expect(await screen.findByText("Hiện có: 9")).toBeInTheDocument();
});

test("Bỏ deletes the draft", async () => {
  const key = draftKey(ME.account.id, 7);
  localStorage.setItem(key, draftOf({ [AN_TX1]: { text: "7", expected: null } }));
  await renderApp("/gradebook/7", gradebookApi([]));
  const banner = await screen.findByRole("region", { name: "Bản nháp chưa lưu" });
  expect(localStorage.getItem(key)).not.toBeNull(); // looking at it does not touch it
  fireEvent.click(within(banner).getByRole("button", { name: "Bỏ" }));
  expect(screen.queryByRole("region", { name: "Bản nháp chưa lưu" })).not.toBeInTheDocument();
  expect(localStorage.getItem(key)).toBeNull();
  expect(await cell("An, TX1")).toHaveValue("");
});

test("a draft older than a week is ignored and removed", async () => {
  const key = draftKey(ME.account.id, 7);
  localStorage.setItem(
    key,
    draftOf({ [AN_TX1]: { text: "7", expected: null } }, DRAFT_LIFETIME_MS + 60_000),
  );
  await renderApp("/gradebook/7", gradebookApi([]));
  await cell("An, TX1");
  expect(screen.queryByRole("region", { name: "Bản nháp chưa lưu" })).not.toBeInTheDocument();
  expect(localStorage.getItem(key)).toBeNull();
});

test("a reader is not offered a draft, and a draft cell of a student who left is not restored", async () => {
  const key = draftKey(ME.account.id, 7);
  localStorage.setItem(key, draftOf({ [AN_TX1]: { text: "7", expected: null } }));
  await renderApp("/gradebook/7", gradebookApi([], undefined, { can_enter: false }));
  await screen.findByRole("rowheader", { name: "An" });
  expect(screen.queryByRole("region", { name: "Bản nháp chưa lưu" })).not.toBeInTheDocument();
  cleanup();
  localStorage.setItem(key, draftOf({ "1:13": { text: "7", expected: 91 } })); // Cường left
  await renderApp("/gradebook/7", gradebookApi([]));
  await screen.findByRole("rowheader", { name: "An" });
  expect(screen.queryByRole("region", { name: "Bản nháp chưa lưu" })).not.toBeInTheDocument();
});

test("signing out removes this person's drafts and keeps another person's", async () => {
  const mine = draftKey(ME.account.id, 7);
  const other = draftKey(ME.account.id + 1, 7);
  localStorage.setItem(mine, draftOf({ [AN_TX1]: { text: "7", expected: null } }));
  localStorage.setItem(
    draftKey(ME.account.id, 9),
    draftOf({ [AN_TX1]: { text: "6", expected: null } }),
  );
  localStorage.setItem(other, draftOf({ [AN_TX1]: { text: "5", expected: null } }));
  const confirm = vi.fn((_message: string) => true);
  vi.stubGlobal("confirm", confirm);
  const { history } = await renderApp("/", (r) => {
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
    if (r.url.endsWith("/api/auth/logout/")) return { status: 204 };
  });
  fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
  await waitFor(() => expect(history.location.pathname).toBe("/login"));
  expect(String(confirm.mock.calls[0]?.[0])).toContain("Còn 2 ô điểm chưa lưu");
  expect(localStorage.getItem(mine)).toBeNull();
  expect(localStorage.getItem(draftKey(ME.account.id, 9))).toBeNull();
  expect(localStorage.getItem(other)).not.toBeNull();
});

test("a sign-out that is declined, or that the server refuses, keeps the drafts", async () => {
  const key = draftKey(ME.account.id, 7);
  localStorage.setItem(key, draftOf({ [AN_TX1]: { text: "7", expected: null } }));
  const confirm = vi.fn((_message: string) => false);
  vi.stubGlobal("confirm", confirm);
  const { history } = await renderApp("/", (r) => {
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
    if (r.url.endsWith("/api/auth/logout/")) return { status: 403 };
  });
  fireEvent.click(await screen.findByRole("button", { name: "Đăng xuất" }));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(history.location.pathname).toBe("/");
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Đăng xuất" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Chưa đăng xuất được");
  expect(localStorage.getItem(key)).not.toBeNull();
});

test("a session that ends keeps the drafts and does not stop at the leave prompt", async () => {
  const confirm = vi.fn((_message: string) => false);
  vi.stubGlobal("confirm", confirm);
  let signedIn = true;
  const { history } = await renderApp("/gradebook/7", (r) => {
    if (r.url.endsWith("/api/auth/me/"))
      return signedIn ? { status: 200, body: ME } : { status: 403 };
    return signedIn ? gradebookApi([])(r) : { status: 403 };
  });
  fireEvent.change(await cell("An, TX1"), { target: { value: "7" } });
  signedIn = false; // the session ends: the next query gets a 403
  history.push("/login");
  await waitFor(() => expect(history.location.pathname).toBe("/login"));
  expect(confirm).not.toHaveBeenCalled();
  expect(readDraft(draftKey(ME.account.id, 7))).toEqual({
    [AN_TX1]: { text: "7", expected: null },
  });
});
