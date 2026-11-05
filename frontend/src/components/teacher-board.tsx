import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { myGradebooksQuery } from "@/api/grades";
import { Ticket } from "@/components/ticket";
import { Button } from "@/components/ui/button";

/** "Hồ sơ khác của cô" on the teacher home: the teacher's gradebooks as tickets in three columns
 * by state (DESIGN.md, Screens). Only Đang nhập has tickets until the workflow arrives. */
export function TeacherBoard() {
  const mine = useQuery(myGradebooksQuery);
  const open = (mine.data ?? []).flatMap((pair) =>
    pair.terms
      .filter((term) => term.gradebook !== null && term.status === "draft")
      .map((term) => ({ pair, term, id: term.gradebook as number })),
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
        <section className="grid content-start gap-4" aria-labelledby="board-open">
          <h3 id="board-open" className="text-sm font-semibold">
            Đang nhập
          </h3>
          {mine.isPending && <p className="italic text-ink-3">Đang tải…</p>}
          {mine.data && open.length === 0 && (
            <p className="italic text-ink-3">Chưa có sổ điểm nào đang nhập.</p>
          )}
          {open.map(({ pair, term, id }) => (
            <Ticket
              key={id}
              pin="open"
              state="Sổ điểm"
              reference={`${pair.subject_name} · lớp ${pair.class_name} · ${term.term_name}`}
            >
              <Button asChild variant="quiet" className="justify-self-start">
                <Link to="/gradebook/$gradebookId" params={{ gradebookId: String(id) }}>
                  Vào sổ
                </Link>
              </Button>
            </Ticket>
          ))}
        </section>
        <section className="grid content-start gap-4" aria-labelledby="board-waiting">
          <h3 id="board-waiting" className="text-sm font-semibold">
            Chờ người khác
          </h3>
          <p className="italic text-ink-3">Không có hồ sơ nào đang chờ người khác duyệt.</p>
        </section>
        <section className="grid content-start gap-4" aria-labelledby="board-locked">
          <h3 id="board-locked" className="text-sm font-semibold">
            Đã khoá
          </h3>
          <p className="italic text-ink-3">Chưa có hồ sơ nào đã khoá.</p>
        </section>
      </div>
    </section>
  );
}
