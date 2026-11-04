import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { LeaveRequest } from "@/api/leave";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const TODAY = new Date().toLocaleDateString("sv");

type Mutable<T> = { -readonly [K in keyof T]: T[K] };

function LEAVE(fields: Partial<Mutable<LeaveRequest>> = {}): Mutable<LeaveRequest> {
  return {
    id: 1,
    student: 11,
    student_name: "An",
    class_name: "7A",
    sent_by: 3,
    sent_by_name: "Chị Hoa",
    from_on: "2026-11-05",
    to_on: "2026-11-06",
    reason: "Con ốm",
    status: "waiting",
    sent_at: "2026-11-04T01:00:00Z",
    decided_by: null,
    decided_by_name: null,
    decided_at: null,
    decision_comment: "",
    ...fields,
  };
}

const TEACHER = {
  ...ME,
  capabilities: [
    {
      action: "leave_request.approve",
      scopes: [{ kind: "homeroom_class", access: "write", once_released: false }],
    },
  ],
};

/** What was posted, as path and body. */
async function sent(posts: Request[]) {
  return Promise.all(
    posts.map(async (p) => {
      const text = await p.clone().text(); // a cancel has no body
      return { path: new URL(p.url).pathname, body: text ? JSON.parse(text) : undefined };
    }),
  );
}

/** The leave API on a list the test can change; `posts` keeps each POST. */
function leaveApi(list: Mutable<LeaveRequest>[], posts: Request[] = []) {
  return (r: Request) => {
    const { pathname, searchParams } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: TEACHER };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
    if (pathname === "/api/setup/leave-requests/children/")
      return {
        status: 200,
        body: [
          { id: 11, name: "An", class_name: "7A" },
          { id: 12, name: "Bình", class_name: "7B" },
        ],
      };
    if (pathname === "/api/setup/leave-requests/" && r.method === "GET") {
      const status = searchParams.get("status");
      return { status: 200, body: list.filter((l) => !status || l.status === status) };
    }
    if (r.method === "POST") {
      posts.push(r.clone());
      const action = pathname.split("/").at(-2);
      const id = Number(pathname.split("/").at(-3));
      const target = list.find((l) => l.id === id);
      if (target && action === "approve") target.status = "approved";
      if (target && action === "decline") target.status = "declined";
      if (target && action === "cancel") target.status = "cancelled";
      return { status: 200, body: target ?? LEAVE() };
    }
  };
}

test("the teacher home pins one ticket per waiting request and approving takes it off", async () => {
  const list = [LEAVE(), LEAVE({ id: 2, student: 12, student_name: "Bình", reason: "Việc nhà" })];
  const posts: Request[] = [];
  await renderApp("/", leaveApi(list, posts));
  const inbox = await screen.findByRole("complementary", { name: "Cần cô xử lý" });
  const tickets = await within(inbox).findAllByRole("article");
  expect(tickets).toHaveLength(2);
  expect(tickets[0]).toHaveTextContent("An · lớp 7A");
  expect(tickets[0]).toHaveTextContent("05/11/2026 – 06/11/2026");
  expect(tickets[0]).toHaveTextContent("Con ốm");
  expect(tickets[0]).toHaveTextContent("Gửi bởi Chị Hoa");

  fireEvent.click(within(tickets[0] as HTMLElement).getByRole("button", { name: "Duyệt" }));
  await waitFor(async () =>
    expect(await sent(posts)).toEqual([
      { path: "/api/setup/leave-requests/1/approve/", body: { comment: "" } },
    ]),
  );
  await waitFor(() => expect(within(inbox).getAllByRole("article")).toHaveLength(1));
  expect(within(inbox).queryByText("Con ốm")).not.toBeInTheDocument();
});

test("declining a request needs a reason, and says nothing to the server without one", async () => {
  const posts: Request[] = [];
  await renderApp("/", leaveApi([LEAVE()], posts));
  const ticket = await screen.findByRole("article");
  fireEvent.click(within(ticket).getByRole("button", { name: "Từ chối" }));
  const reason = within(ticket).getByLabelText("Lý do từ chối, An");

  fireEvent.click(within(ticket).getByRole("button", { name: "Gửi từ chối" }));
  expect(await within(ticket).findByText(/Cần ghi lý do từ chối/)).toBeInTheDocument();
  expect(reason).toHaveAttribute("aria-invalid", "true");
  expect(reason).toHaveFocus();
  expect(await sent(posts)).toEqual([]);

  fireEvent.change(reason, { target: { value: "  Đã nghỉ nhiều  " } });
  fireEvent.click(within(ticket).getByRole("button", { name: "Gửi từ chối" }));
  await waitFor(async () =>
    expect(await sent(posts)).toEqual([
      { path: "/api/setup/leave-requests/1/decline/", body: { comment: "Đã nghỉ nhiều" } },
    ]),
  );
  expect(await screen.findByText(/Không có đơn xin nghỉ nào đang chờ/)).toBeInTheDocument();
});

test("a teacher who decides no leave requests has no Cần cô xử lý column", async () => {
  await renderApp("/", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
  });
  await screen.findByText("Hôm nay bạn không có tiết nào.");
  expect(screen.queryByText("Cần cô xử lý")).not.toBeInTheDocument();
});

test("the Guardian view shows the requests by state, the declined one with its comment in red", async () => {
  const list = [
    LEAVE({ id: 4, status: "cancelled" }),
    LEAVE({
      id: 3,
      status: "declined",
      decided_by_name: "Cô Lan",
      decision_comment: "Đã nghỉ nhiều",
    }),
    LEAVE({ id: 2, status: "approved", decided_by_name: "Cô Lan" }),
    LEAVE({ id: 1 }),
  ];
  const posts: Request[] = [];
  await renderApp("/guardian", leaveApi(list, posts));
  const sentList = await screen.findByRole("list", { name: "Các đơn đã gửi" });
  const tickets = await within(sentList).findAllByRole("article");
  expect(tickets.map((t) => t.querySelector("p.font-serif")?.textContent)).toEqual([
    "Đã huỷ",
    "Từ chối",
    "Đã duyệt",
    "Đang chờ",
  ]);
  expect(within(tickets[1] as HTMLElement).getByText(/Đã nghỉ nhiều/).className).toContain(
    "text-destructive",
  );
  expect(tickets[2]).toHaveTextContent("Duyệt bởi Cô Lan");
  // Only the waiting one can be cancelled.
  expect(screen.getAllByRole("button", { name: "Huỷ đơn" })).toHaveLength(1);
  fireEvent.click(within(tickets[3] as HTMLElement).getByRole("button", { name: "Huỷ đơn" }));
  await waitFor(async () =>
    expect(await sent(posts)).toEqual([
      { path: "/api/setup/leave-requests/1/cancel/", body: undefined },
    ]),
  );
  await waitFor(() => expect(screen.queryByRole("button", { name: "Huỷ đơn" })).toBeNull());
});

test("the Guardian picks a child among pills and sends the days with a reason", async () => {
  const posts: Request[] = [];
  await renderApp("/guardian", leaveApi([], posts));
  const second = await screen.findByRole("radio", { name: "Bình" });
  expect(screen.getByRole("radio", { name: "An" })).toBeChecked();
  fireEvent.click(second);
  fireEvent.change(screen.getByLabelText("Từ ngày"), { target: { value: "2030-02-04" } });
  fireEvent.change(screen.getByLabelText("Đến hết ngày"), { target: { value: "2030-02-06" } });
  fireEvent.change(screen.getByLabelText("Lý do"), { target: { value: " Đi khám " } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi đơn" }));
  await waitFor(async () =>
    expect(await sent(posts)).toEqual([
      {
        path: "/api/setup/leave-requests/",
        body: { student: 12, from_on: "2030-02-04", to_on: "2030-02-06", reason: "Đi khám" },
      },
    ]),
  );
  expect(await screen.findByText(/Đã gửi đơn/)).toBeInTheDocument();
  expect(TODAY).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});

test("a refused send names the field, or says the days are taken", async () => {
  await renderApp("/guardian", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/leave-requests/" && r.method === "POST")
      return { status: 400, body: { to_on: ["range_too_long"] } };
    return leaveApi([])(r);
  });
  fireEvent.change(await screen.findByLabelText("Lý do"), { target: { value: "Đi xa" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi đơn" }));
  const toOn = await screen.findByLabelText("Đến hết ngày");
  await waitFor(() => expect(toOn).toHaveAttribute("aria-invalid", "true"));
  expect(screen.getByText("Một đơn xin nghỉ tối đa 30 ngày.")).toBeInTheDocument();
  expect(toOn).toHaveFocus();
});

test("days already covered by a waiting or approved request are the form's message", async () => {
  await renderApp("/guardian", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/setup/leave-requests/" && r.method === "POST")
      return { status: 400, body: { constraint: ["leaverequest_no_overlap"] } };
    return leaveApi([])(r);
  });
  fireEvent.change(await screen.findByLabelText("Lý do"), { target: { value: "Đi xa" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi đơn" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("đã có đơn xin nghỉ");
});

const SHEET = (students: unknown[]) => ({
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
  can_take: true,
  students,
});
const ON_LEAVE = { id: 9, from_on: TODAY, to_on: TODAY };

function sheetApi(students: unknown[]) {
  return (r: Request) => {
    const { pathname } = new URL(r.url);
    if (pathname === `/api/setup/attendance/1/${TODAY}/`)
      return { status: 200, body: SHEET(students) };
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
  };
}

test("an untaken sheet starts a student with an approved leave as absent with leave", async () => {
  await renderApp(
    `/attendance/1/${TODAY}`,
    sheetApi([
      { id: 11, name: "An", mark: null, leave: ON_LEAVE },
      { id: 12, name: "Bảo", mark: null, leave: null },
    ]),
  );
  const an = await screen.findByRole("group", { name: "An" });
  expect(within(an).getByRole("radio", { name: "Vắng có phép" })).toBeChecked();
  expect(screen.getByLabelText("Ghi chú, An")).toHaveValue("Có đơn xin nghỉ");
  expect(screen.getAllByText("Có đơn")).toHaveLength(1);
  const bao = screen.getByRole("group", { name: "Bảo" });
  expect(within(bao).getByRole("radio", { name: "Có mặt" })).toBeChecked();
  expect(screen.getByLabelText("Ghi chú, Bảo")).toHaveValue("");
});

test("a taken sheet keeps its marks and only flags the leave", async () => {
  await renderApp(
    `/attendance/1/${TODAY}`,
    sheetApi([
      { id: 11, name: "An", mark: { status: "present", note: "" }, leave: ON_LEAVE },
      { id: 12, name: "Bảo", mark: { status: "late", note: "xe" }, leave: null },
      // Joined the class after the sheet was taken: no mark, and not defaulted from the leave.
      { id: 13, name: "Chi", mark: null, leave: ON_LEAVE },
    ]),
  );
  const an = await screen.findByRole("group", { name: "An" });
  expect(within(an).getByRole("radio", { name: "Có mặt" })).toBeChecked();
  expect(screen.getByLabelText("Ghi chú, An")).toHaveValue("");
  expect(screen.getAllByText("Có đơn")).toHaveLength(2);
  const chi = screen.getByRole("group", { name: "Chi" });
  expect(within(chi).getByRole("radio", { name: "Có mặt" })).toBeChecked();
  expect(screen.getByLabelText("Ghi chú, Chi")).toHaveValue("");
  expect(
    within(screen.getByRole("group", { name: "Bảo" })).getByRole("radio", { name: "Muộn" }),
  ).toBeChecked();
});
