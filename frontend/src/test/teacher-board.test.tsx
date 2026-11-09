import { screen, within } from "@testing-library/react";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const TEACHES = { action: "scores.enter", scopes: [{ kind: "teaching_pair", access: "write" }] };
const REVIEWS = {
  action: "gradebook.review",
  scopes: [{ kind: "subject_group", access: "write" }],
};

const TERM = (
  term: number,
  name: string,
  gradebook: number | null,
  status: string | null,
  returned = false,
) => ({
  term,
  term_name: name,
  gradebook,
  status,
  returned,
});

const MINE = [
  {
    subject: 2,
    subject_name: "Toán",
    school_class: 5,
    class_name: "7A",
    terms: [TERM(1, "HK I", 7, "draft", true), TERM(2, "HK II", 8, "draft")],
  },
  {
    subject: 3,
    subject_name: "Lý",
    school_class: 5,
    class_name: "7A",
    terms: [TERM(1, "HK I", 9, "submitted"), TERM(2, "HK II", 10, "approved")],
  },
];

const REVIEW_ITEM = {
  id: 21,
  school_year: 1,
  term: 1,
  term_name: "HK I",
  subject: 4,
  subject_name: "Hoá",
  assessment: "scored",
  school_class: 6,
  class_name: "8B",
  status: "submitted",
  opened_at: "2026-11-04T08:00:00+07:00",
  submitted_by_name: "Thầy Minh",
  submitted_at: "2026-11-05T09:00:00Z",
};

async function openHome(capabilities: unknown[]) {
  const paths: string[] = [];
  await renderApp("/", (r) => {
    const { pathname, search } = new URL(r.url);
    paths.push(pathname + search);
    if (pathname === "/api/auth/me/") return { status: 200, body: { ...ME, capabilities } };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
    if (pathname === "/api/setup/gradebooks/mine/") return { status: 200, body: MINE };
    if (pathname === "/api/setup/gradebooks/7/")
      return {
        status: 200,
        body: { id: 7, return_comment: "Sửa điểm của Bảo", steps: [], can: [] },
      };
    if (pathname === "/api/setup/gradebooks/" && search === "?to_review=1")
      return { status: 200, body: [REVIEW_ITEM] };
  });
  return paths;
}

test("the board groups the teacher's other gradebooks by status", async () => {
  await openHome([TEACHES]);
  const open = await screen.findByRole("region", { name: "Đang nhập" });
  expect(await within(open).findByText("Toán · lớp 7A · HK II")).toBeInTheDocument();
  expect(within(open).queryByText(/HK I$/)).not.toBeInTheDocument(); // returned: in Cần cô xử lý
  const waiting = screen.getByRole("region", { name: "Chờ người khác" });
  expect(within(waiting).getByText("Lý · lớp 7A · HK I")).toBeInTheDocument();
  expect(within(waiting).getByRole("link", { name: "Mở sổ" })).toHaveAttribute(
    "href",
    "/gradebook/9",
  );
  const locked = screen.getByRole("region", { name: "Đã khoá" });
  expect(within(locked).getByText("Lý · lớp 7A · HK II")).toBeInTheDocument();
  expect(within(locked).getByRole("link", { name: "Mở sổ" })).toHaveAttribute(
    "href",
    "/gradebook/10",
  );
});

test("Cần cô xử lý pins a returned gradebook with its comment in red ink", async () => {
  await openHome([TEACHES]);
  const inbox = await screen.findByRole("complementary", { name: "Cần cô xử lý" });
  expect(await within(inbox).findByText("Toán · lớp 7A · HK I")).toBeInTheDocument();
  const comment = await within(inbox).findByText("Sửa điểm của Bảo");
  expect(comment.className).toContain("text-destructive");
  expect(within(inbox).getByRole("link", { name: "Mở sổ" })).toHaveAttribute(
    "href",
    "/gradebook/7",
  );
});

test("a reviewer sees the gradebooks waiting for them, and a teacher alone does not ask", async () => {
  const paths = await openHome([REVIEWS]);
  const inbox = await screen.findByRole("complementary", { name: "Cần cô xử lý" });
  expect(await within(inbox).findByText("Hoá · lớp 8B · HK I")).toBeInTheDocument();
  expect(within(inbox).getByText(/Nộp bởi Thầy Minh/)).toBeInTheDocument();
  expect(within(inbox).getByRole("link", { name: "Mở sổ" })).toHaveAttribute(
    "href",
    "/gradebook/21",
  );
  expect(paths).not.toContain("/api/setup/gradebooks/mine/"); // no scores.enter: no board either
  expect(screen.queryByText("Hồ sơ khác của cô")).not.toBeInTheDocument();
});

test("a teacher without a review duty never asks for the review queue", async () => {
  const paths = await openHome([TEACHES]);
  await screen.findByRole("complementary", { name: "Cần cô xử lý" });
  expect(paths.some((p) => p.includes("to_review"))).toBe(false);
});
