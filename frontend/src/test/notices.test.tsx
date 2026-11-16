import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
});

const RECEIVED = [
  {
    id: 2,
    title: "Họp phụ huynh",
    body: "Họp lúc 7 giờ sáng thứ Bảy.",
    sent_at: "2026-11-16T02:00:00Z",
    sender_name: "Cô Lan",
    audience: "class",
    read_at: null as string | null,
  },
  {
    id: 1,
    title: "Nghỉ lễ",
    body: "Trường nghỉ ngày 20/11.",
    sent_at: "2026-11-10T02:00:00Z",
    sender_name: "Thầy Hùng",
    audience: "school",
    read_at: "2026-11-10T03:00:00Z" as string | null,
  },
];

const AUDIENCES = [
  { audience: "school" },
  { audience: "group", subject_group: { id: 3, name: "Toán" } },
  { audience: "homeroom_guardians", school_class: { id: 5, name: "7A" } },
  { audience: "class", school_class: { id: 6, name: "7B" } },
];

const SENT = [
  {
    id: 9,
    title: "Nhắc nộp bài",
    body: "Nộp trước thứ Sáu.",
    sent_at: "2026-11-15T02:00:00Z",
    sender_name: "Cô Lan",
    audience: "class",
    school_class_name: "7B",
    subject_group_name: null,
    recipient_count: 30,
    read_count: 12,
  },
];

/** The notices API: the received list (read marks stick), the sent list, the audiences; `posts`
 * keeps each POST as path and body. */
function noticesApi(
  audiences: unknown[],
  posts: { path: string; body: unknown }[] = [],
  refuse?: { status: number; body: unknown },
) {
  const received = structuredClone(RECEIVED);
  return async (r: Request) => {
    const { pathname, searchParams } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (pathname === "/api/setup/timetable/mine/") return { status: 200, body: [] };
    if (pathname === "/api/setup/notices/audiences/") return { status: 200, body: audiences };
    if (pathname === "/api/setup/notices/" && r.method === "GET")
      return { status: 200, body: searchParams.get("sent") ? SENT : received };
    if (r.method === "POST") {
      const text = await r.clone().text();
      posts.push({ path: pathname, body: text ? JSON.parse(text) : undefined });
      if (pathname.endsWith("/read/")) {
        const target = received.find((n) => n.id === Number(pathname.split("/").at(-3)));
        if (target) target.read_at ??= "2026-11-17T01:00:00Z";
        return { status: 200, body: target };
      }
      return refuse ?? { status: 201, body: SENT[0] };
    }
  };
}

test("the list shows the newest notice first with a dot on the unread one", async () => {
  await renderApp("/notices", noticesApi([]));
  const cards = await screen.findAllByRole("article");
  expect(cards).toHaveLength(2);
  expect(cards[0]).toHaveTextContent("Họp phụ huynh");
  expect(cards[0]).toHaveTextContent("Cô Lan");
  expect(within(cards[0] as HTMLElement).getByLabelText("Chưa đọc")).toBeInTheDocument();
  expect(within(cards[1] as HTMLElement).queryByLabelText("Chưa đọc")).not.toBeInTheDocument();
});

test("opening a notice shows its body and marks it read once", async () => {
  const posts: { path: string; body: unknown }[] = [];
  await renderApp("/notices", noticesApi([], posts));
  const first = within((await screen.findAllByRole("article"))[0] as HTMLElement).getByRole(
    "button",
    { name: "Đọc" },
  );
  expect(screen.queryByText("Họp lúc 7 giờ sáng thứ Bảy.")).not.toBeInTheDocument();
  fireEvent.click(first);
  expect(await screen.findByText("Họp lúc 7 giờ sáng thứ Bảy.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByLabelText("Chưa đọc")).not.toBeInTheDocument());
  fireEvent.click(first); // close
  fireEvent.click(first); // open again: already read, no second POST
  expect(posts).toEqual([{ path: "/api/setup/notices/2/read/", body: undefined }]);
});

test("a member who may send nothing sees no Đã gửi tab and no composer", async () => {
  await renderApp("/notices", noticesApi([]));
  await screen.findAllByRole("article");
  expect(screen.queryByRole("tab", { name: "Đã gửi" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Gửi thông báo" })).not.toBeInTheDocument();
});

test("a sender sees Đã gửi with the counts of recipients and reads", async () => {
  await renderApp("/notices", noticesApi(AUDIENCES));
  const tab = await screen.findByRole("tab", { name: "Đã gửi" });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
  expect(await screen.findByText("30 người nhận · 12 đã đọc")).toBeInTheDocument();
  expect(screen.getByText("Nhắc nộp bài")).toBeInTheDocument();
});

test("the composer builds the audience select from the stub, in Vietnamese", async () => {
  await renderApp("/notices", noticesApi(AUDIENCES));
  fireEvent.click(await screen.findByRole("button", { name: "Gửi thông báo" }));
  const select = await screen.findByLabelText("Gửi đến");
  expect(
    within(select)
      .getAllByRole("option")
      .map((o) => o.textContent),
  ).toEqual(["Toàn trường", "Tổ Toán", "Phụ huynh lớp 7A", "Phụ huynh và học sinh lớp 7B"]);
});

test("a refused title is worded under its field and takes focus", async () => {
  const posts: { path: string; body: unknown }[] = [];
  await renderApp(
    "/notices",
    noticesApi(AUDIENCES, posts, { status: 400, body: { title: ["too_long"] } }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Gửi thông báo" }));
  fireEvent.change(await screen.findByLabelText("Gửi đến"), { target: { value: "class:6" } });
  fireEvent.change(screen.getByLabelText("Tiêu đề"), { target: { value: "x" } });
  fireEvent.change(screen.getByLabelText("Nội dung"), { target: { value: "Xin chào" } });
  expect(screen.getByText("8 / 5000")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  expect(await screen.findByText("Tiêu đề tối đa 200 ký tự.")).toBeInTheDocument();
  expect(posts).toEqual([
    {
      path: "/api/setup/notices/",
      body: {
        audience: "class",
        school_class: 6,
        subject_group: null,
        title: "x",
        body: "Xin chào",
      },
    },
  ]);
  const title = screen.getByLabelText("Tiêu đề");
  expect(title).toHaveAttribute("aria-invalid", "true");
  await waitFor(() => expect(title).toHaveFocus());
});

test("a sent notice closes the composer and refreshes Đã gửi", async () => {
  await renderApp("/notices", noticesApi(AUDIENCES));
  fireEvent.click(await screen.findByRole("button", { name: "Gửi thông báo" }));
  fireEvent.change(await screen.findByLabelText("Tiêu đề"), { target: { value: "Chào" } });
  fireEvent.change(screen.getByLabelText("Nội dung"), { target: { value: "Xin chào" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() => expect(screen.queryByLabelText("Tiêu đề")).not.toBeInTheDocument());
});
