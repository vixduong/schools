import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { schoolClock } from "@/lib/timetable";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const AN = { id: 11, name: "Nguyễn An", class_name: "7A", left: false };
const BINH = { id: 12, name: "Nguyễn Bình", class_name: "9B", left: false };

const PERIOD = {
  session: "morning",
  number: 1,
  starts_at: "07:00:00",
  ends_at: "07:45:00",
  subject_name: "Toán",
  teacher_name: "Cô Lan",
  room_name: "P101",
  status: "late",
};

const DAY: Record<number, unknown> = {
  11: {
    on: "2026-11-26",
    periods: [
      PERIOD,
      {
        ...PERIOD,
        number: 2,
        starts_at: "07:50:00",
        ends_at: "08:35:00",
        subject_name: "Ngữ văn",
        status: null,
      },
    ],
  },
  12: {
    on: "2026-11-26",
    periods: [{ ...PERIOD, subject_name: "Hoá học", status: "absent_unexcused" }],
  },
};

const SCORES: Record<number, unknown> = {
  11: {
    term: 1,
    term_name: "Học kỳ I",
    gradebooks: [
      {
        subject_name: "Toán",
        class_name: "7A",
        columns: [
          { kind: "regular", index: 1, value: 8.5, result: null, changed_after_release: false },
          { kind: "mid_term", index: 1, value: 7, result: null, changed_after_release: true },
        ],
      },
    ],
  },
  12: {
    term: 1,
    term_name: "Học kỳ I",
    gradebooks: [
      {
        subject_name: "Thể dục",
        class_name: "9B",
        columns: [
          { kind: "regular", index: 1, value: null, result: "pass", changed_after_release: false },
        ],
      },
    ],
  },
};

const NOTICE = {
  id: 1,
  title: "Họp phụ huynh cuối kỳ",
  body: "…",
  sent_at: "2026-11-20T01:00:00Z",
  sender_name: "Cô Hiệu trưởng",
  audience: "school",
  read_at: null,
};

type Portal = {
  me?: unknown;
  children?: unknown[];
  leaveChildren?: unknown[];
  leaveChildrenStatus?: number;
  day?: Record<number, unknown>;
  scores?: Record<number, unknown>;
  notices?: unknown[];
};

/** The portal API: children, their day and scores, the leave children and received notices. */
function portalApi(p: Portal = {}) {
  return (r: Request) => {
    const { pathname } = new URL(r.url);
    const id = Number(pathname.split("/").at(-3));
    if (pathname === "/api/auth/me/") return { status: 200, body: p.me ?? ME };
    if (pathname === "/api/portal/children/")
      return { status: 200, body: p.children ?? [AN, BINH] };
    if (pathname.endsWith("/today/")) return { status: 200, body: (p.day ?? DAY)[id] };
    if (pathname.endsWith("/scores/")) return { status: 200, body: (p.scores ?? SCORES)[id] };
    if (pathname === "/api/setup/leave-requests/children/")
      return { status: p.leaveChildrenStatus ?? 200, body: p.leaveChildren ?? [AN, BINH] };
    if (pathname === "/api/setup/leave-requests/") return { status: 200, body: [] };
    if (pathname === "/api/setup/notices/") return { status: 200, body: p.notices ?? [NOTICE] };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
  };
}

test("a Guardian with two children switches between them with pills", async () => {
  await renderApp("/guardian", portalApi());
  const today = await screen.findByRole("list", { name: "Các tiết hôm nay" });
  expect(await within(today).findByText("Muộn")).toBeInTheDocument();
  expect(within(today).getByText("Chưa điểm danh")).toBeInTheDocument();
  const scores = await screen.findByRole("region", { name: "Điểm mới" });
  expect(await within(scores).findByText("8,5")).toBeInTheDocument();
  expect(within(scores).getByText("đã sửa")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Nguyễn An" })).toBeChecked();
  expect(screen.getByRole("heading", { name: "Đơn xin nghỉ" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("radio", { name: "Nguyễn Bình" }));
  expect(await screen.findByText("Vắng không phép")).toBeInTheDocument();
  expect(await screen.findByText("Đạt")).toBeInTheDocument();
  expect(screen.queryByText("8,5")).not.toBeInTheDocument();
});

test("a failed leave-children query shows an error instead of hiding Đơn xin nghỉ", async () => {
  await renderApp("/guardian", portalApi({ children: [AN], leaveChildrenStatus: 500 }));
  expect(
    await screen.findByText(/Không tải được danh sách con/, {}, { timeout: 15_000 }),
  ).toBeInTheDocument();
}, 20_000); // the query retries twice before it gives up

test("the same subject in two gradebooks shows each class beside it", async () => {
  const toan = (class_name: string, value: number) => ({
    subject_name: "Toán",
    class_name,
    columns: [{ kind: "regular", index: 1, value, result: null, changed_after_release: false }],
  });
  await renderApp(
    "/guardian",
    portalApi({
      children: [AN],
      scores: {
        11: { term: 1, term_name: "Học kỳ I", gradebooks: [toan("6A", 6), toan("7A", 9)] },
      },
    }),
  );
  const scores = await screen.findByRole("region", { name: "Điểm mới" });
  expect(await within(scores).findByText("Toán · 6A")).toBeInTheDocument();
  expect(within(scores).getByText("Toán · 7A")).toBeInTheDocument();
});

test("a student sees their own day without pills or Đơn xin nghỉ", async () => {
  await renderApp("/guardian", portalApi({ children: [AN], leaveChildren: [] }));
  await screen.findByRole("list", { name: "Các tiết hôm nay" });
  expect(await screen.findByText("Họp phụ huynh cuối kỳ")).toBeInTheDocument();
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Đơn xin nghỉ" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Xem tất cả thông báo" })).toHaveAttribute(
    "href",
    "/notices",
  );
});

test("each block says what is missing when it is empty", async () => {
  await renderApp(
    "/guardian",
    portalApi({
      children: [AN],
      day: { 11: { on: "2026-11-26", periods: [] } },
      scores: { 11: { term: 1, term_name: "Học kỳ I", gradebooks: [] } },
      notices: [],
    }),
  );
  expect(await screen.findByText("Hôm nay không có tiết học nào.")).toBeInTheDocument();
  expect(await screen.findByText("Chưa có điểm nào được công bố.")).toBeInTheDocument();
  expect(await screen.findByText("Chưa có thông báo nào.")).toBeInTheDocument();
});

test("a member with no children sees no portal page", async () => {
  await renderApp("/guardian", portalApi({ children: [] }));
  expect(
    await screen.findByText("Chưa có học sinh nào gắn với tài khoản này."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Học tập" })).not.toBeInTheDocument();
});

test("a member with children and no teacher or admin role lands on /guardian", async () => {
  const { history } = await renderApp("/", portalApi({ children: [AN] }));
  await waitFor(() => expect(history.location.pathname).toBe("/guardian"));
  expect(await screen.findByRole("link", { name: "Học tập" })).toBeInTheDocument();
});

test("a teacher who is also a Guardian stays on the teacher home, with the link", async () => {
  const teacher = {
    ...ME,
    role_assignments: [{ id: 1, role: "subject_teacher", valid_from: "2026-09-01" }],
  };
  const { history } = await renderApp("/", portalApi({ me: teacher, children: [AN] }));
  expect(await screen.findByText("Hôm nay bạn không có tiết nào.")).toBeInTheDocument();
  expect(history.location.pathname).toBe("/");
  expect(await screen.findByRole("link", { name: "Học tập" })).toBeInTheDocument();
});

test("a member with no role and no children stays on the home page", async () => {
  const { history } = await renderApp("/", portalApi({ children: [] }));
  expect(await screen.findByText("Hôm nay bạn không có tiết nào.")).toBeInTheDocument();
  expect(history.location.pathname).toBe("/");
});

test("the School's clock is Asia/Ho_Chi_Minh, whatever the browser's zone", () => {
  expect(schoolClock(new Date("2026-11-25T17:30:00Z"))).toEqual({
    day: "2026-11-26",
    time: "00:30",
  });
  expect(schoolClock(new Date("2026-11-26T01:05:00Z"))).toEqual({
    day: "2026-11-26",
    time: "08:05",
  });
});
