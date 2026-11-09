import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type GradebookDetail, myGradebooksQuery } from "@/api/grades";
import { type Pin, Ticket } from "@/components/ticket";
import { Button } from "@/components/ui/button";

const COLUMNS: {
  status: GradebookDetail["status"];
  title: string;
  pin: Pin;
  link: string;
  empty: string;
}[] = [
  {
    status: "draft",
    title: "Đang nhập",
    pin: "open",
    link: "Vào sổ",
    empty: "Chưa có sổ điểm nào đang nhập.",
  },
  {
    status: "submitted",
    title: "Chờ người khác",
    pin: "waiting",
    link: "Mở sổ",
    empty: "Không có hồ sơ nào đang chờ người khác duyệt.",
  },
  {
    status: "approved",
    title: "Đã khoá",
    pin: "locked",
    link: "Mở sổ",
    empty: "Chưa có hồ sơ nào đã khoá.",
  },
];

/** "Hồ sơ khác của cô" on the teacher home: the teacher's gradebooks as tickets in three columns
 * by state (DESIGN.md, Screens). A returned gradebook is in Cần cô xử lý, not here. */
export function TeacherBoard() {
  const mine = useQuery(myGradebooksQuery);
  const tickets = (mine.data ?? []).flatMap((pair) =>
    pair.terms.flatMap((term) =>
      term.gradebook !== null && term.status && !term.returned
        ? [{ pair, term, id: term.gradebook, status: term.status }]
        : [],
    ),
  );
  return (
    <section aria-labelledby="board" className="mt-12 grid gap-4">
      <h2 id="board" className="font-serif text-2xl font-light">
        Hồ sơ khác của cô
      </h2>
      {mine.isError && (
        <p role="alert" className="text-destructive">
          Không tải được các sổ điểm. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      <div className="grid items-start gap-8 md:grid-cols-3">
        {COLUMNS.map((column) => {
          const here = tickets.filter((t) => t.status === column.status);
          return (
            <section
              key={column.status}
              className="grid content-start gap-4"
              aria-labelledby={`board-${column.status}`}
            >
              <h3 id={`board-${column.status}`} className="text-sm font-semibold">
                {column.title}
              </h3>
              {mine.isPending && column.status === "draft" && (
                <p className="italic text-ink-3">Đang tải…</p>
              )}
              {mine.data && here.length === 0 && (
                <p className="italic text-ink-3">{column.empty}</p>
              )}
              {here.map(({ pair, term, id }) => (
                <Ticket
                  key={id}
                  pin={column.pin}
                  state="Sổ điểm"
                  reference={`${pair.subject_name} · lớp ${pair.class_name} · ${term.term_name}`}
                >
                  <Button asChild variant="quiet" className="justify-self-start">
                    <Link to="/gradebook/$gradebookId" params={{ gradebookId: String(id) }}>
                      {column.link}
                    </Link>
                  </Button>
                </Ticket>
              ))}
            </section>
          );
        })}
      </div>
    </section>
  );
}
