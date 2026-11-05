import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { gradebookQuery } from "@/api/grades";
import { GradebookGrid } from "@/components/gradebook-grid";

export const Route = createFileRoute("/_app/gradebook/$gradebookId")({ component: Screen });

function Screen() {
  const { gradebookId } = Route.useParams();
  const book = useQuery(gradebookQuery(Number(gradebookId)));
  return (
    <section className="grid gap-4">
      <p>
        <Link to="/gradebook" className="text-sm underline underline-offset-4">
          Các sổ điểm
        </Link>
      </p>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <h1 className="font-serif text-4xl font-light">Sổ điểm</h1>
        {book.data && (
          // The lifecycle shows its first state only until the workflow arrives.
          <span className="rounded-full border-[1.5px] border-foreground bg-foreground px-3 py-0.5 text-sm text-background">
            <span className="sr-only">Trạng thái: </span>
            Đang nhập
          </span>
        )}
      </div>
      {book.isPending && <p className="italic text-ink-3">Đang tải sổ điểm…</p>}
      {book.isError && (
        <p role="alert" className="text-destructive">
          Không mở được sổ điểm. Sổ có thể không tồn tại, hoặc bạn không có quyền xem; kiểm tra mạng
          rồi tải lại trang.
        </p>
      )}
      {book.data && (
        <>
          <p className="italic text-ink-3">
            <span className="font-semibold not-italic text-foreground">
              {book.data.subject_name}
            </span>{" "}
            · lớp {book.data.class_name} · {book.data.term_name} · theo {book.data.profile_source}
          </p>
          <GradebookGrid key={book.data.id} book={book.data} />
        </>
      )}
    </section>
  );
}
