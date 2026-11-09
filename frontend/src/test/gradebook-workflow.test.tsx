import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, type Reply, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const STEP = (action: string, comment = "") => ({
  action,
  by_name: "Cô Lan",
  at: "2026-11-04T15:40:00Z",
  comment,
});

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
    columns: [{ id: 1, kind: "regular", index: 1, released_at: null }],
    students: [
      {
        id: 11,
        name: "An",
        in_class: true,
        cells: [{ column: 1, entry: 90, value: 7, result: null, changed_after_release: false }],
      },
      { id: 12, name: "Bảo", in_class: true, cells: [] },
    ],
    ...over,
  };
}

/** The gradebook 7 with `detail`; each step POST is kept (cloned) and answered by `reply`. */
async function openBook(
  detail: Record<string, unknown>,
  reply: () => Reply = () => ({ status: 200, body: DETAIL() }),
) {
  const posts: Request[] = [];
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/gradebooks/7/") return { status: 200, body: DETAIL(detail) };
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (r.method === "POST" && pathname.startsWith("/api/setup/gradebooks/7/")) {
      posts.push(r.clone());
      return reply();
    }
  });
  return posts;
}

test("a draft shows Đang nhập, with the cells open and only the buttons the server allows", async () => {
  await openBook({ can: ["submit"] });
  const chips = await screen.findByRole("list", { name: "Trạng thái sổ điểm" });
  expect(within(chips).getByText("Đang nhập").closest("li")).toHaveAttribute(
    "aria-current",
    "step",
  );
  expect(within(chips).getByText("Chờ duyệt").closest("li")).not.toHaveAttribute("aria-current");
  expect(within(chips).getByText("Đã khoá")).toBeInTheDocument();
  expect(await screen.findByRole("textbox", { name: "An, TX1" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Nộp sổ" })).toBeInTheDocument();
  for (const name of ["Rút lại để sửa", "Duyệt", "Trả lại", "Mở lại"])
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
});

test("a submitted gradebook locks the cells and offers Rút lại để sửa without asking", async () => {
  const posts = await openBook({ status: "submitted", can: ["withdraw"], steps: [STEP("submit")] });
  expect(await screen.findByRole("rowheader", { name: "An" })).toBeInTheDocument();
  const chips = screen.getByRole("list", { name: "Trạng thái sổ điểm" });
  expect(within(chips).getByText("Chờ duyệt").closest("li")).toHaveAttribute(
    "aria-current",
    "step",
  );
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Lưu" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Rút lại để sửa" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(new URL(posts[0]?.url ?? "").pathname).toBe("/api/setup/gradebooks/7/withdraw/");
});

test("a returned draft shows the comment in red ink above the grid, and the steps list under it", async () => {
  await openBook({
    can: ["submit"],
    return_comment: "Sửa điểm của Bảo",
    steps: [STEP("submit"), STEP("return", "Sửa điểm của Bảo")],
  });
  const note = await screen.findByRole("region", { name: "Sổ bị trả lại" });
  expect(note).toHaveTextContent("Sửa điểm của Bảo");
  expect(note).toHaveTextContent("Cô Lan");
  expect(note.className).toContain("text-destructive");
  const steps = screen.getByRole("list", { name: "Các bước của sổ" });
  const items = within(steps).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Đã nộp");
  expect(items[1]).toHaveTextContent("Trả lại");
  expect(items[1]).toHaveTextContent("Sửa điểm của Bảo");
});

test("Nộp sổ asks first, and an incomplete answer marks the empty cells Chưa có điểm", async () => {
  const posts = await openBook({ can: ["submit"] }, () => ({
    status: 400,
    body: { cells: [{ column: 1, student: 12, code: "incomplete" }] },
  }));
  fireEvent.click(await screen.findByRole("button", { name: "Nộp sổ" }));
  const dialog = await screen.findByRole("dialog", { name: "Nộp sổ điểm?" });
  expect(posts).toHaveLength(0); // the click that asks sends nothing
  fireEvent.click(within(dialog).getByRole("button", { name: "Nộp sổ" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const empty = screen.getByRole("textbox", { name: "Bảo, TX1" });
  expect(empty).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByText("Chưa có điểm")).toBeInTheDocument();
  expect(empty).toHaveFocus();
});

test("Nộp sổ waits for the typed cells to be saved", async () => {
  await openBook({ can: ["submit"] });
  fireEvent.change(await screen.findByRole("textbox", { name: "Bảo, TX1" }), {
    target: { value: "8" },
  });
  expect(screen.getByRole("button", { name: "Nộp sổ" })).toBeDisabled();
});

test("Duyệt asks first; a refusal for one's own submission has its words", async () => {
  const posts = await openBook({ status: "submitted", can: ["approve", "return"] }, () => ({
    status: 400,
    body: { status: ["own_submission"] },
  }));
  fireEvent.click(await screen.findByRole("button", { name: "Duyệt" }));
  const dialog = await screen.findByRole("dialog", { name: "Duyệt sổ điểm?" });
  expect(posts).toHaveLength(0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Duyệt" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("không tự duyệt");
  expect(new URL(posts[0]?.url ?? "").pathname).toBe("/api/setup/gradebooks/7/approve/");
});

const DRF_DENIED = { detail: "You do not have permission to perform this action." };

test.each([
  ["a lost role", 403, DRF_DENIED, /không còn quyền/],
  [
    "a failed CSRF check",
    403,
    { detail: "CSRF Failed: CSRF token missing." },
    /Không thực hiện được/,
  ],
  ["a concurrent enrolment", 400, { constraint: ["gradebook_incomplete"] }, /vừa đổi trạng thái/],
])("Duyệt refused for %s says it in words", async (_name, status, body, words) => {
  await openBook({ status: "submitted", can: ["approve"] }, () => ({ status, body }));
  fireEvent.click(await screen.findByRole("button", { name: "Duyệt" }));
  const dialog = await screen.findByRole("dialog", { name: "Duyệt sổ điểm?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Duyệt" }));
  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent(words);
  expect(alert).not.toHaveTextContent("liên hệ nhà trường");
});

test("a reason over 500 characters is told so, not asked for again", async () => {
  await openBook({ status: "submitted", can: ["approve", "return"] }, () => ({
    status: 400,
    body: { comment: ["too_long"] },
  }));
  fireEvent.click(await screen.findByRole("button", { name: "Trả lại" }));
  const dialog = await screen.findByRole("dialog", { name: "Trả lại sổ điểm?" });
  fireEvent.change(within(dialog).getByRole("textbox", { name: "Lý do trả lại" }), {
    target: { value: "x" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Trả lại" }));
  expect(await within(dialog).findByText(/tối đa 500 ký tự/)).toBeInTheDocument();
  expect(within(dialog).queryByText(/Cần ghi lý do/)).not.toBeInTheDocument();
});

test("Trả lại needs a comment, and sends it", async () => {
  const posts = await openBook({ status: "submitted", can: ["approve", "return"] });
  fireEvent.click(await screen.findByRole("button", { name: "Trả lại" }));
  const dialog = await screen.findByRole("dialog", { name: "Trả lại sổ điểm?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Trả lại" }));
  const field = within(dialog).getByRole("textbox", { name: "Lý do trả lại" });
  expect(field).toHaveAttribute("aria-invalid", "true");
  expect(field).toHaveFocus();
  expect(within(dialog).getByText(/Cần ghi lý do trả lại/)).toBeInTheDocument();
  expect(posts).toHaveLength(0);
  fireEvent.change(field, { target: { value: " Sửa điểm của Bảo " } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Trả lại" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(new URL(posts[0]?.url ?? "").pathname).toBe("/api/setup/gradebooks/7/return/");
  expect(await posts[0]?.json()).toEqual({ comment: "Sửa điểm của Bảo" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("Mở lại says every change is logged, needs a reason, and sends it", async () => {
  const posts = await openBook({ status: "approved", can: ["reopen"], steps: [STEP("approve")] });
  fireEvent.click(await screen.findByRole("button", { name: "Mở lại" }));
  const dialog = await screen.findByRole("dialog", { name: "Mở lại sổ điểm?" });
  expect(dialog).toHaveTextContent("ghi lại");
  fireEvent.click(within(dialog).getByRole("button", { name: "Mở lại" }));
  const field = within(dialog).getByRole("textbox", { name: "Lý do mở lại" });
  expect(field).toHaveAttribute("aria-invalid", "true");
  expect(posts).toHaveLength(0);
  fireEvent.change(field, { target: { value: "Nhập nhầm điểm" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Mở lại" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(new URL(posts[0]?.url ?? "").pathname).toBe("/api/setup/gradebooks/7/reopen/");
  expect(await posts[0]?.json()).toEqual({ reason: "Nhập nhầm điểm" });
});
