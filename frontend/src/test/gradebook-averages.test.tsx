import { screen, within } from "@testing-library/react";
import { ME, renderApp } from "./render-app";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

const avg = (over: Record<string, unknown> = {}) => ({
  value: null,
  result: null,
  state: "final",
  missing: [],
  carried: false,
  reason: null,
  ...over,
});

const row = (id: number, name: string, semester: object, year: object | null = null) => ({
  id,
  name,
  in_class: true,
  left_on: null,
  can_carry: false,
  arrival: null,
  carried: [],
  cells: [],
  averages: { semester, year },
});

function BOOK(students: object[], over: Record<string, unknown> = {}) {
  return {
    id: 7,
    school_year: 1,
    term: 2,
    term_name: "HK II",
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
      { id: 3, kind: "end_term", index: 1, released_at: null },
    ],
    students,
    ...over,
  };
}

async function openBook(book: object) {
  await renderApp("/gradebook/7", (r) => {
    const { pathname } = new URL(r.url);
    if (pathname === "/api/auth/me/") return { status: 200, body: ME };
    if (pathname === "/api/setup/gradebooks/7/") return { status: 200, body: book };
  });
}

const cell = (label: RegExp) => screen.findByLabelText(label);

test("the average columns follow the score columns and come before the arrivals column", async () => {
  await openBook(
    BOOK([
      {
        ...row(11, "An", avg({ value: 7.4 }), avg({ value: 7.2 })),
        arrival: {
          arrived_on: "2026-11-02",
          source_school: null,
          document_name: null,
          recorded_at: null,
        },
      },
    ]),
  );
  await cell(/^An, ĐTB/);
  const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
  expect(heads.slice(0, 7)).toEqual([
    "Học sinh",
    "TX1",
    "GK",
    "CK",
    "ĐTB",
    "Cả năm",
    "Từ trường cũ",
  ]);
});

test("a final average is plain figures with a decimal comma, also on the year", async () => {
  await openBook(BOOK([row(11, "An", avg({ value: 7.4 }), avg({ value: 7.2 }))]));
  const semester = await cell(/^An, ĐTB/);
  expect(semester).toHaveAccessibleName("An, ĐTB: 7,4");
  expect(semester).toHaveTextContent(/^7,4$/);
  expect(semester.className).not.toContain("italic");
  expect(screen.getByLabelText(/^An, Cả năm/)).toHaveAccessibleName("An, Cả năm: 7,2");
});

test("a provisional average is italic and marked tạm, in words for screen readers too", async () => {
  await openBook(
    BOOK([
      row(
        11,
        "An",
        avg({ value: 7.4, state: "provisional" }),
        avg({ value: 7.2, state: "provisional" }),
      ),
    ]),
  );
  const semester = await cell(/^An, ĐTB/);
  expect(semester).toHaveTextContent("7,4 tạm");
  expect(semester.className).toContain("italic");
  expect(semester).toHaveAccessibleName("An, ĐTB: 7,4 tạm");
});

test("a missing average is a dash naming the empty columns in its title and label", async () => {
  const missing = avg({
    state: "missing",
    missing: [
      { kind: "regular", index: 2 },
      { kind: "end_term", index: 1 },
    ],
  });
  await openBook(BOOK([row(11, "An", missing, missing)]));
  const semester = await cell(/^An, ĐTB/);
  expect(semester).toHaveTextContent(/^—$/);
  expect(semester).toHaveAttribute("title", "Thiếu điểm TX2, CK");
  expect(semester).toHaveAccessibleName("An, ĐTB: chưa có. Thiếu điểm TX2, CK");
});

test("a year missing only because the semester 1 book is incomplete says so, never a blank title", async () => {
  await openBook(BOOK([row(11, "An", avg({ value: 8 }), avg({ state: "missing" }))]));
  const year = await cell(/^An, Cả năm/);
  expect(year).toHaveTextContent(/^—$/);
  expect(year).toHaveAttribute("title", "Sổ học kỳ trước còn thiếu điểm");
});

test("left, split and unavailable show a dash with the reason in the title", async () => {
  await openBook(
    BOOK([
      row(11, "An", avg({ state: "left" }), avg({ state: "left" })),
      row(12, "Bảo", avg({ state: "split" }), avg({ state: "split" })),
      row(
        13,
        "Cường",
        avg({ state: "unavailable", reason: "rules" }),
        avg({ state: "unavailable", reason: "rules" }),
      ),
    ]),
  );
  const left = await cell(/^An, ĐTB/);
  expect(left).toHaveTextContent(/^—$/);
  expect(left).toHaveAttribute("title", "Học sinh đã rời lớp");
  expect(screen.getByLabelText(/^Bảo, ĐTB/)).toHaveAttribute(
    "title",
    "Học sinh đổi lớp trong học kỳ, điểm nằm ở hai sổ",
  );
  const rules = screen.getByLabelText(/^Cường, Cả năm/);
  expect(rules).toHaveTextContent(/^—$/);
  expect(rules).toHaveAttribute("title", "Quy định đánh giá thiếu cách tính điểm trung bình");
  expect(rules).toHaveAccessibleName(
    "Cường, Cả năm: chưa có. Quy định đánh giá thiếu cách tính điểm trung bình",
  );
});

test("a year without exactly two terms shows the year column as a dash naming why", async () => {
  await openBook(
    BOOK([row(11, "An", avg({ value: 7.4 }), avg({ state: "unavailable", reason: "terms" }))], {
      term_name: "HK I",
    }),
  );
  const year = await cell(/^An, Cả năm/);
  expect(year).toHaveTextContent(/^—$/);
  expect(year).toHaveAttribute("title", "Năm học không có đúng hai học kỳ");
});

test("an arriving student without a previous semester average reads it in red ink on the year cell", async () => {
  await openBook(
    BOOK([
      row(11, "An", avg({ value: 8 }), avg({ state: "missing", reason: "no_previous_average" })),
    ]),
  );
  const year = await cell(/^An, Cả năm/);
  expect(year).toHaveTextContent("Chưa có TB học kỳ trước");
  expect(year.className).toContain("text-destructive");
  expect(year).toHaveAccessibleName("An, Cả năm: Chưa có TB học kỳ trước");
});

test("a semester 1 book has no year column", async () => {
  await openBook(BOOK([row(11, "An", avg({ value: 7.4 }))], { term_name: "HK I" }));
  await cell(/^An, ĐTB/);
  expect(screen.queryByRole("columnheader", { name: "Cả năm" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Cả năm/)).not.toBeInTheDocument();
});

test("a comment-only subject shows Kết quả as Đạt or Chưa đạt", async () => {
  await openBook(
    BOOK(
      [
        row(11, "An", avg({ result: "pass" }), avg({ result: "pass" })),
        row(
          12,
          "Bảo",
          avg({ result: "fail", state: "provisional" }),
          avg({ result: "fail", state: "provisional" }),
        ),
      ],
      { assessment: "comment_only" },
    ),
  );
  expect(await cell(/^An, Kết quả/)).toHaveAccessibleName("An, Kết quả: Đạt");
  const fail = screen.getByLabelText(/^Bảo, Kết quả/);
  expect(fail).toHaveTextContent("Chưa đạt tạm");
  expect(fail).toHaveAccessibleName("Bảo, Kết quả: Chưa đạt tạm");
  expect(
    within(screen.getByRole("table")).getByRole("columnheader", { name: "Cả năm" }),
  ).toBeInTheDocument();
});
