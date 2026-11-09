import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { gradebookQuery, gradebooksToReviewQuery, myGradebooksQuery } from "@/api/grades";
import { Ticket } from "@/components/ticket";
import { Button } from "@/components/ui/button";
import { stamp } from "@/lib/grades";

function OpenBook({ id }: { id: number }) {
  return (
    <Button asChild variant="quiet" className="mt-2 justify-self-start">
      <Link to="/gradebook/$gradebookId" params={{ gradebookId: String(id) }}>
        Mở sổ
      </Link>
    </Button>
  );
}

/** Cần cô xử lý, the teacher's part: a pinned ticket per gradebook sent back to them. */
export function ReturnedTickets() {
  const mine = useQuery(myGradebooksQuery);
  const returned = (mine.data ?? []).flatMap((pair) =>
    pair.terms.flatMap((term) =>
      term.gradebook !== null && term.returned ? [{ pair, term, id: term.gradebook }] : [],
    ),
  );
  return (
    <>
      {mine.isError && (
        <p role="alert" className="text-destructive">
          Không tải được các sổ điểm. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {mine.data && returned.length === 0 && (
        <p className="italic text-ink-3">Không có sổ điểm nào bị trả lại.</p>
      )}
      {returned.map(({ pair, term, id }) => (
        <ReturnedTicket
          key={id}
          id={id}
          reference={`${pair.subject_name} · lớp ${pair.class_name} · ${term.term_name}`}
        />
      ))}
    </>
  );
}

// The list names a return, not its words: the comment is read from the gradebook, which the
// person opens next anyway.
function ReturnedTicket({ id, reference }: { id: number; reference: string }) {
  const book = useQuery(gradebookQuery(id));
  return (
    <Ticket pin="alert" state="Sổ bị trả lại" reference={reference}>
      {book.data?.return_comment && <p className="text-destructive">{book.data.return_comment}</p>}
      <OpenBook id={id} />
    </Ticket>
  );
}

/** Cần cô xử lý, the reviewer's part: a pinned ticket per submitted gradebook waiting for them. */
export function ReviewTickets() {
  const waiting = useQuery(gradebooksToReviewQuery);
  return (
    <>
      {waiting.isError && (
        <p role="alert" className="text-destructive">
          Không tải được các sổ điểm chờ duyệt. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {waiting.data?.length === 0 && (
        <p className="italic text-ink-3">Không có sổ điểm nào đang chờ cô duyệt.</p>
      )}
      {waiting.data?.map((book) => (
        <Ticket
          key={book.id}
          pin="waiting"
          state="Chờ cô duyệt"
          reference={`${book.subject_name} · lớp ${book.class_name} · ${book.term_name}`}
        >
          {book.submitted_by_name && book.submitted_at && (
            <p className="text-sm text-ink-3">
              Nộp bởi {book.submitted_by_name}, {stamp(book.submitted_at)}
            </p>
          )}
          <OpenBook id={book.id} />
        </Ticket>
      ))}
    </>
  );
}
