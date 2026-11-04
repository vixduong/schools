import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const TODAY = new Date().toLocaleDateString("sv");

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
  attendance: null,
};

function SHEET(canTake = true) {
  return {
    entry: 1,
    on: TODAY,
    session: "morning",
    number: 1,
    starts_at: "07:00:00",
    ends_at: "07:45:00",
    school_class: 5,
    class_name: "7A",
    subject: 2,
    subject_name: "Toán",
    room_name: "P101",
    can_take: canTake,
    students: [
      { id: 11, name: "An", mark: null },
      { id: 12, name: "Bảo", mark: null },
    ],
  };
}

function sheetApi(posts: unknown[], canTake = true) {
  return (r: Request) => {
    const { pathname } = new URL(r.url);
    if (pathname === `/api/setup/attendance/1/${TODAY}/`) {
      if (r.method === "PUT") {
        posts.push(r.clone());
        return { status: 200, body: SHEET(canTake) };
      }
      return { status: 200, body: SHEET(canTake) };
    }
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
  };
}

test("the home shows each period's attendance result, and the current period carries Điểm danh", async () => {
  const periods = [
    PERIOD,
    { ...PERIOD, id: 2, starts_at: "23:59:58", attendance: { absent: 2, late: 1 } },
    { ...PERIOD, id: 3, starts_at: "23:59:58", attendance: { absent: 0, late: 0 } },
  ];
  await renderApp("/", (r) => {
    if (r.url.endsWith("/api/setup/timetable/mine/")) return { status: 200, body: periods };
    if (r.url.endsWith("/api/auth/me/")) return { status: 200, body: ME };
  });
  const list = await screen.findByRole("list", { name: "Các tiết hôm nay" });
  const [first, second, third] = within(list).getAllByRole("listitem") as [
    HTMLElement,
    HTMLElement,
    HTMLElement,
  ];
  expect(first).toHaveTextContent("Chưa điểm danh");
  expect(second).toHaveTextContent("Vắng 2 · Muộn 1");
  expect(third).toHaveTextContent("Đủ");
  // The current period (the first) links to its sheet; the others carry a plain link.
  const action = within(first).getByRole("link", { name: "Điểm danh" });
  expect(action).toHaveAttribute("href", `/attendance/1/${TODAY}`);
  expect(action.className).toContain("bg-primary");
  expect(within(second).getByRole("link", { name: "Điểm danh" }).className).not.toContain(
    "bg-primary",
  );
});

test("the sheet starts with everyone present and saves the whole class with changes and notes", async () => {
  const posts: Request[] = [];
  await renderApp(`/attendance/1/${TODAY}`, sheetApi(posts as unknown[]));
  const bao = await screen.findByRole("group", { name: "Bảo" });
  expect(within(bao).getByRole("radio", { name: "Có mặt" })).toBeChecked();
  expect(screen.getByText("Chưa lưu.")).toBeInTheDocument();

  fireEvent.click(within(bao).getByRole("radio", { name: "Vắng có phép" }));
  fireEvent.change(screen.getByLabelText("Ghi chú, Bảo"), { target: { value: "ốm" } });
  expect(screen.getByText("Có thay đổi chưa lưu.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

  await waitFor(() => expect(posts).toHaveLength(1));
  expect(await posts[0]?.json()).toEqual({
    marks: [
      { student: 11, status: "present", note: "" },
      { student: 12, status: "absent_excused", note: "ốm" },
    ],
  });
  expect(await screen.findByText(/^Đã lưu lúc/)).toBeInTheDocument();
});

test("a reader without attendance.take sees the sheet read only", async () => {
  await renderApp(`/attendance/1/${TODAY}`, sheetApi([], false));
  const an = await screen.findByRole("group", { name: "An" });
  expect(within(an).getByRole("radio", { name: "Có mặt" })).toBeDisabled();
  expect(screen.getByLabelText("Ghi chú, An")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Lưu" })).not.toBeInTheDocument();
  expect(screen.getByText("Bạn chỉ xem được bảng điểm danh này.")).toBeInTheDocument();
});

test("a refused save keeps the sheet and says the class may have changed", async () => {
  await renderApp(`/attendance/1/${TODAY}`, (r) => {
    if (r.method === "PUT")
      return { status: 400, body: { students: { missing: [13], extra: [] } } };
    return sheetApi([])(r);
  });
  await screen.findByRole("group", { name: "An" });
  fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Danh sách lớp có thể đã thay đổi");
  expect(screen.getByRole("group", { name: "An" })).toBeInTheDocument();
});
