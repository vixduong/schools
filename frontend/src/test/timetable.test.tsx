import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const PERIOD = {
  id: 1,
  session: "morning",
  number: 1,
  starts_at: "00:00:00",
  ends_at: "23:59:59",
  school_class: 5,
  class_name: "7A",
  subject: 2,
  subject_name: "Toán",
  room: 3,
  room_name: "P101",
};
const LATER = {
  ...PERIOD,
  id: 2,
  number: 2,
  starts_at: "23:59:58",
  ends_at: "23:59:59",
  room_name: null,
};

const ADMIN = {
  ...ME,
  capabilities: [{ action: "school.configure", scopes: [{ kind: "school", access: "write" }] }],
};

function me(r: Request, body: unknown) {
  if (r.url.endsWith("/api/auth/me/")) return { status: 200, body };
}

test("the teacher's home lists today's periods, the current one marked, with no timetable link", async () => {
  await renderApp("/", (r) => {
    if (r.url.endsWith("/api/setup/timetable/mine/")) return { status: 200, body: [PERIOD, LATER] };
    return me(r, ME);
  });
  const list = await screen.findByRole("list", { name: "Các tiết hôm nay" });
  const [first, second] = within(list).getAllByRole("listitem");
  expect(first).toHaveTextContent("7A");
  expect(first).toHaveTextContent("Toán");
  expect(first).toHaveTextContent("P101");
  expect(first).toHaveAttribute("aria-current", "time");
  expect(second).not.toHaveAttribute("aria-current");
  expect(screen.queryByRole("link", { name: "Thời khóa biểu" })).not.toBeInTheDocument();
});

test("a day without periods says so", async () => {
  await renderApp("/", (r) =>
    r.url.endsWith("/api/setup/timetable/mine/") ? { status: 200, body: [] } : me(r, ME),
  );
  expect(await screen.findByText("Hôm nay bạn không có tiết nào.")).toBeInTheDocument();
});

test("the admin saves a week and a clash names the other entry in red ink", async () => {
  const posts: unknown[] = [];
  const tomorrow = new Date(Date.now() + 86_400_000).toLocaleDateString("sv");
  await renderApp("/timetable", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/classes/5/timetable/" && r.method === "POST") {
      posts.push(r);
      return {
        status: 400,
        body: {
          constraint: ["timetableentry_teacher_clash"],
          clash: { weekday: 1, bell_period: 7, class: 6, subject: 2, teacher: 9, room: null },
        },
      };
    }
    const lists: Record<string, unknown> = {
      "/api/setup/school-years/": [
        { id: 1, name: "2026-2027", starts_on: "2000-01-01", ends_on: "2999-12-31" },
      ],
      "/api/setup/classes/": [
        { id: 5, school_year: 1, grade: 1, name: "7A" },
        { id: 6, school_year: 1, grade: 1, name: "7B" },
      ],
      "/api/setup/subjects/": [{ id: 2, name: "Toán", code: "MATH", is_active: true }],
      "/api/setup/rooms/": [],
      "/api/setup/role-assignments/": [9, 10, 11].map((membership, i) => ({
        id: i + 1,
        membership,
        role: "subject_teacher",
        school_class: 5,
        subject: 2,
        valid_from: membership === 11 ? "2999-01-01" : "2000-01-01",
        valid_to: null,
        status: "active",
      })),
      "/api/setup/memberships/": [
        { id: 9, display_name: "Cô Hoa", status: "active" },
        { id: 10, display_name: "Thầy Nam", status: "inactive" },
        { id: 11, display_name: "Cô Lan", status: "active" },
      ],
      "/api/setup/bell-periods/": [
        {
          id: 7,
          school_year: 1,
          session: "morning",
          number: 1,
          starts_at: "07:00:00",
          ends_at: "07:45:00",
        },
      ],
      "/api/setup/classes/5/timetable/": [],
    };
    if (pathname in lists) return { status: 200, body: lists[pathname] };
    return me(r, ADMIN);
  });

  fireEvent.change(await screen.findByLabelText("Môn, Thứ 2, Sáng 1"), { target: { value: "2" } });
  // Only active members, and only those whose role has started on the day the week applies from.
  const picker = screen.getByLabelText("Giáo viên, Thứ 2, Sáng 1");
  const offered = () =>
    within(picker)
      .getAllByRole("option")
      .map((o) => o.textContent);
  expect(offered()).toEqual(["Giáo viên", "Cô Hoa"]);
  expect(screen.getByLabelText("Áp dụng từ ngày")).toHaveValue(tomorrow); // never today
  fireEvent.change(screen.getByLabelText("Áp dụng từ ngày"), { target: { value: "2999-06-01" } });
  expect(offered()).toEqual(["Giáo viên", "Cô Hoa", "Cô Lan"]);
  fireEvent.change(screen.getByLabelText("Áp dụng từ ngày"), { target: { value: tomorrow } });
  fireEvent.change(picker, { target: { value: "9" } });
  expect(screen.getByLabelText("Áp dụng từ ngày")).toHaveValue(tomorrow);
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(
    "Giáo viên đã có tiết vào Thứ 2, Sáng 1: lớp 7B, môn Toán, Cô Hoa.",
  );
  await waitFor(() => expect(posts).toHaveLength(1));
});
