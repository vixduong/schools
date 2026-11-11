import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { File as NodeFile } from "node:buffer";
import { ME, type Reply, renderApp } from "./render-app";

// Node's File: the FormData the client builds is undici's, which refuses jsdom's File.
const pdf = (content: string) =>
  new NodeFile([content], "eve.pdf", { type: "application/pdf" }) as unknown as File;

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const ARRIVAL = {
  arrived_on: "2026-11-02",
  source_school: null as string | null,
  document_name: null as string | null,
  recorded_at: null as string | null,
};

function DETAIL(eve: Record<string, unknown> = {}, over: Record<string, unknown> = {}) {
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
    can_enter: false,
    steps: [],
    return_comment: null,
    can: [],
    columns: [
      { id: 1, kind: "regular", index: 1, released_at: null },
      { id: 2, kind: "mid_term", index: 1, released_at: null },
    ],
    students: [
      {
        id: 11,
        name: "An",
        in_class: true,
        left_on: null,
        can_carry: false,
        arrival: null,
        carried: [],
        cells: [],
      },
      {
        id: 12,
        name: "Dũng",
        in_class: false,
        left_on: "2026-11-05",
        can_carry: false,
        arrival: null,
        carried: [],
        cells: [],
      },
      {
        id: 13,
        name: "Eve",
        in_class: true,
        left_on: null,
        can_carry: false,
        arrival: ARRIVAL,
        carried: [],
        cells: [],
        ...eve,
      },
    ],
    ...over,
  };
}

const RECORDED = {
  ...ARRIVAL,
  source_school: "THCS Lê Lợi",
  document_name: "eve.pdf",
  recorded_at: "2026-11-03T02:00:00Z",
};
const CARRIED = [
  { kind: "regular", index: 1, value: 8, result: null },
  { kind: "mid_term", index: 1, value: 6.5, result: null },
];

type Sent = { method: string; path: string; request: Request };

async function openBook(
  eve: Record<string, unknown>,
  reply: (sent: Sent) => Reply | undefined = () => undefined,
) {
  const sent: Sent[] = [];
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (r.method === "GET" && pathname === "/api/setup/gradebooks/7/")
      return { status: 200, body: DETAIL(eve) };
    if (r.method !== "GET") {
      const item = { method: r.method, path: pathname, request: r.clone() };
      sent.push(item);
      return reply(item);
    }
  });
  return sent;
}

test("an arriving student shows the arrival, the source School, the document and the carried results beside the columns", async () => {
  await openBook({ arrival: RECORDED, carried: CARRIED });
  const row = (await screen.findByRole("rowheader", { name: /Eve/ })).closest("tr");
  expect(row).toHaveTextContent("Chuyển đến 02/11");
  expect(row).toHaveTextContent("THCS Lê Lợi");
  const link = within(row as HTMLElement).getByRole("link", { name: "Hồ sơ chuyển" });
  expect(link).toHaveAttribute("href", "/api/setup/gradebooks/7/students/13/transfer/document/");
  expect(screen.getByRole("columnheader", { name: "Từ trường cũ" })).toBeInTheDocument();
  expect(within(row as HTMLElement).getByLabelText("Kết quả mang sang của Eve")).toHaveTextContent(
    "TX1 8 · GK 6,5",
  );
  // The School's own cells are untouched and read only here.
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  // Only the homeroom teacher (can_carry) gets the button.
  expect(screen.queryByRole("button", { name: /Nhập kết quả mang sang/ })).not.toBeInTheDocument();
});

test("a student who left keeps a greyed row with the leaving date, and has no arrival group", async () => {
  await openBook({ arrival: null });
  const row = (await screen.findByRole("rowheader", { name: /Dũng/ })).closest("tr");
  expect(row).toHaveTextContent("đã rời lớp từ 05/11");
  expect(row?.className).toContain("text-ink-3");
  expect(screen.queryByRole("columnheader", { name: "Từ trường cũ" })).not.toBeInTheDocument();
});

test("the homeroom teacher records the document and the results: the file first, then the results", async () => {
  const sent = await openBook({ arrival: ARRIVAL, can_carry: true }, ({ path }) => {
    if (path.endsWith("/transfer/")) return { status: 201, body: DETAIL() };
    if (path.endsWith("/carried/")) return { status: 200, body: DETAIL() };
  });
  fireEvent.click(await screen.findByRole("button", { name: "Nhập kết quả mang sang, Eve" }));
  const dialog = await screen.findByRole("dialog", { name: /Kết quả mang sang: Eve/ });
  fireEvent.change(within(dialog).getByLabelText("Trường cũ"), {
    target: { value: "THCS Lê Lợi" },
  });
  const file = pdf("%PDF-1.7");
  fireEvent.change(within(dialog).getByLabelText("Hồ sơ chuyển"), { target: { files: [file] } });
  fireEvent.change(within(dialog).getByLabelText("TX1"), { target: { value: "8" } });
  fireEvent.change(within(dialog).getByLabelText("GK"), { target: { value: "6,5" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
  await waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[0]?.path).toBe("/api/setup/gradebooks/7/students/13/transfer/");
  expect(sent[0]?.request.headers.get("content-type")).toContain("multipart/form-data");
  const body = (await sent[0]?.request.text()) ?? "";
  expect(body).toContain("THCS Lê Lợi");
  // jsdom's FormData cannot carry the file's bytes here (a real browser does); the field is sent.
  expect(body).toContain('name="document"');
  expect(sent[1]?.method).toBe("PUT");
  expect(await sent[1]?.request.json()).toEqual({
    results: [
      { kind: "regular", index: 1, value: 8, result: null },
      { kind: "mid_term", index: 1, value: 6.5, result: null },
    ],
  });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("a first record needs the document, and a refused file or score is worded on its field", async () => {
  const sent = await openBook({ arrival: ARRIVAL, can_carry: true }, ({ path }) =>
    path.endsWith("/transfer/")
      ? { status: 400, body: { document: ["unsupported_type"] } }
      : undefined,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Nhập kết quả mang sang, Eve" }));
  const dialog = await screen.findByRole("dialog", { name: /Kết quả mang sang: Eve/ });
  fireEvent.change(within(dialog).getByLabelText("Trường cũ"), { target: { value: "THCS X" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
  expect(await within(dialog).findByText("Cần tải hồ sơ chuyển.")).toBeInTheDocument();
  expect(sent).toHaveLength(0); // refused here, nothing sent
  const file = pdf("hello");
  fireEvent.change(within(dialog).getByLabelText("Hồ sơ chuyển"), { target: { files: [file] } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
  expect(await within(dialog).findByText("Chỉ nhận PDF, JPEG hoặc PNG.")).toBeInTheDocument();
  // A score that is not a number is refused before anything is sent for it.
  fireEvent.change(within(dialog).getByLabelText("TX1"), { target: { value: "abc" } });
  expect(sent).toHaveLength(1);
});

test("changing only the school of a recorded transfer asks for the document again and sends nothing", async () => {
  const sent = await openBook({ arrival: RECORDED, can_carry: true });
  fireEvent.click(await screen.findByRole("button", { name: "Nhập kết quả mang sang, Eve" }));
  const dialog = await screen.findByRole("dialog", { name: /Kết quả mang sang: Eve/ });
  fireEvent.change(within(dialog).getByLabelText("Trường cũ"), { target: { value: "THCS Khác" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Lưu" }));
  expect(
    await within(dialog).findByText("Đổi trường cũ thì cần tải lại hồ sơ chuyển."),
  ).toBeInTheDocument();
  expect(sent).toHaveLength(0);
});

test("a submitted gradebook says so in the dialog and disables Lưu", async () => {
  const sent: Request[] = [];
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (r.method === "GET" && pathname === "/api/setup/gradebooks/7/")
      return {
        status: 200,
        body: DETAIL({ arrival: RECORDED, can_carry: true }, { status: "submitted" }),
      };
    sent.push(r);
  });
  fireEvent.click(await screen.findByRole("button", { name: "Nhập kết quả mang sang, Eve" }));
  const dialog = await screen.findByRole("dialog", { name: /Kết quả mang sang: Eve/ });
  expect(within(dialog).getByText("Sổ đã nộp, không sửa được.")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Lưu" })).toBeDisabled();
  expect(sent).toHaveLength(0);
});
