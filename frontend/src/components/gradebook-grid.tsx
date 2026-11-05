import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import { History } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import {
  type CellError,
  type CellInput,
  type CurrentEntry,
  cellHistoryQuery,
  GRADEBOOK_KEY,
  type GradebookCell,
  type GradebookColumn,
  type GradebookDetail,
  type GradebookRow,
  gradebookQuery,
} from "@/api/grades";
import { meQuery } from "@/api/queries";
import { FormError } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type DraftEdit, draftKey, readDraft, writeDraft } from "@/lib/drafts";
import {
  CELL_ERROR,
  columnLabel,
  formatScore,
  NOT_A_NUMBER,
  type Parsed,
  parseScore,
  RESULTS,
  resultLabel,
  stamp,
} from "@/lib/grades";
import { NETWORK } from "@/lib/messages";
import { cn } from "@/lib/utils";

const GENERIC =
  "Không lưu được điểm. Danh sách lớp có thể đã thay đổi: tải lại trang rồi lưu lại; các ô bạn nhập vẫn còn.";

type Edit = DraftEdit;
type Problem = { code: CellError["code"] | "invalid"; current?: CurrentEntry | null };

const keyOf = (column: number, student: number) => `${column}:${student}`;

/** A cell's saved text: "7,5" for a scored subject, "pass" or "fail" for a comment-only one. */
function savedText(cell: GradebookCell | undefined, commentOnly: boolean): string {
  if (!cell) return "";
  return commentOnly ? (cell.result ?? "") : formatScore(cell.value);
}

/** The server refused the save cell by cell. */
class CellsRefused extends Error {
  constructor(readonly cells: CellError[]) {
    super("cells");
  }
}

/** A body is a cell-by-cell refusal only when every item names a cell and a code we can word:
 * anything else under `cells` (a malformed request) is the generic message. */
function isCellErrors(cells: unknown): cells is CellError[] {
  return (
    Array.isArray(cells) &&
    cells.length > 0 &&
    cells.every(
      (c) =>
        typeof c?.column === "number" && typeof c?.student === "number" && c.code in CELL_ERROR,
    )
  );
}

/** The enrolled students a column still lacks a score for. */
class Incomplete extends Error {
  constructor(readonly names: string[]) {
    super("incomplete");
  }
}

function cellInput(key: string, edit: Edit, parsed: Parsed, commentOnly: boolean): CellInput {
  const [column, student] = key.split(":").map(Number) as [number, number];
  if (commentOnly) {
    const result = RESULTS.find((r) => r.value === edit.text)?.value ?? null;
    return { column, student, value: null, result, expected: edit.expected };
  }
  return {
    column,
    student,
    value: parsed.kind === "value" ? parsed.value : null,
    expected: edit.expected,
  };
}

/** The dense grid: students as rows, one column per assessment. Typed cells are kept in `edits`
 * until the server confirms them; a failed save never clears them. */
export function GradebookGrid({ book }: { book: GradebookDetail }) {
  const queryClient = useQueryClient();
  const { data: me } = useSuspenseQuery(meQuery);
  const commentOnly = book.assessment === "comment_only";
  const editable = book.can_enter;
  const draftId = draftKey(me.account.id, book.id);

  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [problems, setProblems] = useState<Record<string, Problem>>({});
  const [failure, setFailure] = useState<string>();
  const [historyOf, setHistoryOf] = useState<string | null>(null);
  const [releasing, setReleasing] = useState<GradebookColumn | null>(null);
  const [refusedFirst, setRefusedFirst] = useState<string | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement | HTMLSelectElement>());
  const latest = useRef(edits);
  latest.current = edits;

  // The draft of an earlier visit, offered (never applied) until the person chooses. Only the
  // cells of students still in the class and columns of this grid can be restored.
  const [pending, setPending] = useState<Record<string, Edit> | null>(() => {
    const draft = editable ? readDraft(draftId) : null;
    const open = new Set(
      book.students
        .filter((s) => s.in_class)
        .flatMap((s) => book.columns.map((c) => keyOf(c.id, s.id))),
    );
    const usable = Object.entries(draft ?? {}).filter(([key]) => open.has(key));
    return usable.length ? Object.fromEntries(usable) : null;
  });

  const saved = useMemo(
    () =>
      new Map(
        book.students.flatMap((s) => s.cells.map((c) => [keyOf(c.column, s.id), c] as const)),
      ),
    [book],
  );
  const names = useMemo(() => new Map(book.students.map((s) => [s.id, s.name])), [book]);
  const labels = useMemo(() => new Map(book.columns.map((c) => [c.id, columnLabel(c)])), [book]);

  const dirty = Object.keys(edits).length;
  const failed = Object.keys(problems).length;

  // Every change of the edits is kept in the browser until the server confirms the cells. The
  // first run is the mount, which must not renew an old draft's age.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (editable) writeDraft(draftId, { ...pending, ...edits });
  }, [edits, pending, editable, draftId]);

  useBlocker({
    // A session that ends goes to /login and keeps the draft; leaving otherwise asks first.
    shouldBlockFn: ({ next }) =>
      next.pathname !== "/login" &&
      !window.confirm(
        `Còn ${dirty} ô chưa lưu vào sổ điểm. Các ô này còn trong bản nháp trên máy này, nhưng chưa được lưu. Rời trang?`,
      ),
    enableBeforeUnload: dirty > 0,
    disabled: dirty === 0,
  });

  function change(key: string, text: string) {
    setEdits((current) => {
      if (text === savedText(saved.get(key), commentOnly)) {
        const { [key]: _gone, ...rest } = current;
        return rest;
      }
      // An edit keeps the entry it was typed against: a refetch must not move it, or a cell
      // someone else saved meanwhile would be overwritten without a conflict.
      const existing = current[key];
      const expected = existing ? existing.expected : (saved.get(key)?.entry ?? null);
      return { ...current, [key]: { text, expected } };
    });
    setProblems(({ [key]: _gone, ...rest }) => rest);
  }

  function discard(key: string) {
    setEdits(({ [key]: _gone, ...rest }) => rest);
    setProblems(({ [key]: _gone, ...rest }) => rest);
  }

  function restoreDraft() {
    setEdits((current) => ({ ...pending, ...current }));
    setPending(null);
  }

  const save = useMutation({
    mutationFn: async (sent: Record<string, Edit>) => {
      const cells = Object.entries(sent).map(([key, edit]) =>
        cellInput(key, edit, parseScore(edit.text), commentOnly),
      );
      const { data, response, error } = await api.PUT("/api/setup/gradebooks/{id}/cells/", {
        params: { path: { id: book.id } },
        body: { cells },
      });
      if (data) return data;
      const body = error as unknown as { cells?: unknown } | undefined;
      if (response.status === 400 && isCellErrors(body?.cells)) throw new CellsRefused(body.cells);
      if (response.status === 400) throw new Error(GENERIC);
      throw new Error(`HTTP ${response.status}`);
    },
    onSuccess: (data, sent) => {
      // Show the saved cells at once; the refetch below is the server's word.
      queryClient.setQueryData(gradebookQuery(book.id).queryKey, (old) =>
        old ? applySaved(old, sent, data.cells, commentOnly) : old,
      );
      setEdits((current) => {
        const next = { ...current };
        for (const { column, student, entry } of data.cells) {
          const key = keyOf(column, student);
          const typed = next[key];
          if (!typed) continue;
          if (typed.text === sent[key]?.text) delete next[key];
          else next[key] = { ...typed, expected: entry };
        }
        return next;
      });
      setProblems({});
      setFailure(undefined);
    },
    onError: (error, sent) => {
      if (error instanceof CellsRefused) {
        // Only for a cell still holding the text that was sent: a verdict on other text is stale.
        const refused = error.cells.filter((c) => {
          const key = keyOf(c.column, c.student);
          return latest.current[key]?.text === sent[key]?.text;
        });
        setProblems(
          Object.fromEntries(
            refused.map((c) => [keyOf(c.column, c.student), { code: c.code, current: c.current }]),
          ),
        );
        setRefusedFirst(refused[0] ? keyOf(refused[0].column, refused[0].student) : null);
        setFailure(undefined);
      } else {
        // A 400 that is no cell's verdict (a rule only the database holds) has its own words;
        // anything else is a server or network problem, not a verdict on what was typed.
        setFailure(error.message === GENERIC ? GENERIC : NETWORK);
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...GRADEBOOK_KEY, book.id] }),
  });

  function submit() {
    if (!editable || save.isPending || dirty === 0) return;
    // Text that is no score is caught here: NaN would reach the server as null, a clearing.
    const invalid = Object.entries(edits).filter(
      ([, edit]) => !commentOnly && parseScore(edit.text).kind === "invalid",
    );
    if (invalid.length) {
      setProblems((current) => ({
        ...current,
        ...Object.fromEntries(invalid.map(([key]) => [key, { code: "invalid" as const }])),
      }));
      inputs.current.get(invalid[0]?.[0] ?? "")?.focus();
      return;
    }
    save.mutate(edits);
  }

  function focusAt(row: number, column: number, step: [number, number]) {
    const [dr, dc] = step;
    let r = row + dr;
    let c = column + dc;
    while (r >= 0 && r < book.students.length && c >= 0 && c < book.columns.length) {
      const student = book.students[r];
      const col = book.columns[c];
      const input = student && col && inputs.current.get(keyOf(col.id, student.id));
      if (input) {
        input.focus();
        return;
      }
      r += dr;
      c += dc;
    }
  }

  function onKeyDown(event: React.KeyboardEvent, row: number, column: number, key: string) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      submit();
      return;
    }
    if (event.altKey && event.code === "KeyH") {
      event.preventDefault();
      if (saved.get(key)) setHistoryOf(key);
      return;
    }
    // A native select keeps its own arrow keys; Enter still moves on.
    const arrows = !(event.target instanceof HTMLSelectElement);
    const step: Record<string, [number, number] | undefined> = {
      Enter: [event.shiftKey ? -1 : 1, 0],
      ArrowDown: arrows ? [1, 0] : undefined,
      ArrowUp: arrows ? [-1, 0] : undefined,
      ArrowLeft: arrows ? [0, -1] : undefined,
      ArrowRight: arrows ? [0, 1] : undefined,
    };
    const move = step[event.key];
    if (!move) return;
    event.preventDefault();
    focusAt(row, column, move);
  }

  // After a refusal the first refused cell takes focus, once the grid is writable again (a
  // disabled select cannot hold it).
  useEffect(() => {
    if (refusedFirst && !save.isPending) {
      inputs.current.get(refusedFirst)?.focus();
      setRefusedFirst(null);
    }
  }, [refusedFirst, save.isPending]);

  let status = "Đã lưu";
  if (save.isPending) status = "Đang lưu…";
  else if (failed) status = `Lỗi ${failed} ô`;
  else if (dirty) status = `Chưa lưu ${dirty} ô`;

  const conflicts = Object.entries(problems).filter(([, p]) => p.code === "conflict");

  return (
    <div className="grid gap-4">
      {pending && (
        <section
          aria-label="Bản nháp chưa lưu"
          className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm italic text-ink-3"
        >
          <span>Còn {Object.keys(pending).length} ô chưa lưu từ lần trước</span>
          <Button variant="quiet" onClick={restoreDraft}>
            Khôi phục
          </Button>
          <Button variant="quiet" onClick={() => setPending(null)}>
            Bỏ
          </Button>
        </section>
      )}
      {/* One scroll box in both directions: a sticky head and a pinned name column only work
          against the box that scrolls, so it is as tall as the window under the top bar. */}
      <div className="max-h-[calc(100dvh-8rem)] overflow-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Điểm {book.subject_name} lớp {book.class_name}, {book.term_name}
          </caption>
          <thead className="sticky top-0 z-20 bg-background">
            <tr className="border-b border-border">
              <th
                scope="col"
                className="sticky left-0 z-10 bg-background px-2 py-2 text-left font-semibold"
              >
                Học sinh
              </th>
              {book.columns.map((column) => (
                <th key={column.id} scope="col" className="px-2 py-2 text-center align-bottom">
                  <span className="font-semibold">{columnLabel(column)}</span>
                  {column.released_at ? (
                    <span className="block text-xs font-normal italic text-ink-3">đã công bố</span>
                  ) : (
                    editable && (
                      <Button
                        variant="quiet"
                        className="h-auto text-xs font-normal"
                        disabled={dirty > 0 || save.isPending}
                        title={dirty > 0 ? "Lưu các ô đã nhập trước khi công bố" : undefined}
                        aria-label={`Công bố cột ${columnLabel(column)}`}
                        onClick={() => setReleasing(column)}
                      >
                        Công bố cột
                      </Button>
                    )
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {book.students.map((student, row) => (
              <tr
                key={student.id}
                className={cn("border-b border-border", !student.in_class && "text-ink-3")}
              >
                <th
                  scope="row"
                  className="sticky left-0 z-[5] bg-background px-2 py-1 text-left font-normal whitespace-nowrap"
                >
                  {student.name}
                  {!student.in_class && <span className="ml-2 text-xs italic">đã rời lớp</span>}
                </th>
                {book.columns.map((column, col) => {
                  const key = keyOf(column.id, student.id);
                  const cell = saved.get(key);
                  const edit = edits[key];
                  const text = edit?.text ?? savedText(cell, commentOnly);
                  const problem = problems[key];
                  const live = editable && student.in_class;
                  const label = `${student.name}, ${columnLabel(column)}`;
                  return (
                    <td key={column.id} className="group px-1 py-1 text-center align-top">
                      <div className="flex items-center justify-center gap-1">
                        {live ? (
                          <CellField
                            name={label}
                            commentOnly={commentOnly}
                            text={text}
                            locked={save.isPending}
                            invalid={!!problem}
                            describedBy={problem ? `err-${key}` : undefined}
                            refs={inputs.current}
                            cellKey={key}
                            onChange={(value) => change(key, value)}
                            onKeyDown={(event) => onKeyDown(event, row, col, key)}
                          />
                        ) : edit ? (
                          // Typed text on a row that can no longer be scored: shown, never sent
                          // silently, and the person can drop it.
                          <>
                            <span className="inline-block min-w-12 px-2 italic tabular-nums">
                              {textOf(edit.text, commentOnly)}
                            </span>
                            <Button
                              variant="quiet"
                              className="h-auto text-xs font-normal"
                              disabled={save.isPending}
                              aria-label={`Bỏ ô này, ${label}`}
                              onClick={() => discard(key)}
                            >
                              Bỏ ô này
                            </Button>
                          </>
                        ) : (
                          <span className="inline-block min-w-12 px-2 tabular-nums">
                            {commentOnly ? resultLabel(cell?.result) : formatScore(cell?.value)}
                          </span>
                        )}
                        {cell && (
                          <HistoryButton
                            book={book.id}
                            column={column.id}
                            student={student.id}
                            label={label}
                            open={historyOf === key}
                            onOpenChange={(open) => setHistoryOf(open ? key : null)}
                            changed={cell.changed_after_release}
                            tabbable={!live}
                            returnFocusTo={inputs.current.get(key)}
                          />
                        )}
                      </div>
                      {problem && (
                        <p id={`err-${key}`} className="text-xs text-destructive">
                          {problem.code === "invalid" ? NOT_A_NUMBER : CELL_ERROR[problem.code]}
                          {problem.code === "conflict" && problem.current && (
                            <span className="block tabular-nums">
                              Hiện có: {currentText(problem.current, commentOnly)}
                            </span>
                          )}
                        </p>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {book.students.length === 0 && (
        <p className="italic text-ink-3">Chưa có học sinh nào trong lớp trong học kỳ này.</p>
      )}
      {conflicts.length > 0 && (
        <ul className="grid gap-2" aria-label="Ô bị lưu trước">
          {conflicts.map(([key, problem]) => {
            const [column, student] = key.split(":").map(Number) as [number, number];
            const mine = edits[key];
            const current = problem.current;
            return (
              <li key={key} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="text-destructive">
                  {names.get(student)}, {labels.get(column)}: có người vừa lưu{" "}
                  <span className="tabular-nums">
                    {current ? currentText(current, commentOnly) : "ô trống"}
                  </span>
                  {current && ` (${current.entered_by_name}, ${stamp(current.entered_at)})`}. Bạn đã
                  nhập{" "}
                  <span className="tabular-nums">
                    {mine ? textOf(mine.text, commentOnly) : "ô trống"}
                  </span>
                  .
                </span>
                <Button
                  variant="quiet"
                  disabled={save.isPending}
                  aria-label={`Giữ số của tôi, ${names.get(student)} ${labels.get(column)}`}
                  onClick={() => {
                    setEdits((c) => ({
                      ...c,
                      [key]: { text: mine?.text ?? "", expected: current?.entry ?? null },
                    }));
                    setProblems(({ [key]: _gone, ...rest }) => rest);
                  }}
                >
                  Giữ số của tôi
                </Button>
                <Button
                  variant="quiet"
                  disabled={save.isPending}
                  aria-label={`Dùng số đang có, ${names.get(student)} ${labels.get(column)}`}
                  onClick={() => discard(key)}
                >
                  Dùng số đang có
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <FormError message={failure} />
      {editable ? (
        <div className="flex items-center gap-4">
          <Button type="button" onClick={submit} disabled={save.isPending || dirty === 0}>
            Lưu
          </Button>
          <p
            role="status"
            className={cn("text-sm italic", failed ? "text-destructive" : "text-ink-3")}
          >
            {status}
          </p>
        </div>
      ) : (
        <p className="italic text-ink-3">Bạn chỉ xem được sổ điểm này.</p>
      )}
      <ReleaseDialog book={book} column={releasing} onClose={() => setReleasing(null)} />
    </div>
  );
}

function textOf(text: string, commentOnly: boolean): string {
  if (commentOnly) return resultLabel(text) || "ô trống";
  return text.trim() === "" ? "ô trống" : text.trim();
}

function currentText(current: CurrentEntry, commentOnly: boolean): string {
  const text = commentOnly ? resultLabel(current.result) : formatScore(current.value);
  return text || "ô trống";
}

function CellField({
  name,
  commentOnly,
  text,
  locked,
  invalid,
  describedBy,
  refs,
  cellKey,
  onChange,
  onKeyDown,
}: {
  name: string;
  commentOnly: boolean;
  text: string;
  locked: boolean; // a save is in flight: what was sent must not change under it
  invalid: boolean;
  describedBy?: string;
  refs: Map<string, HTMLInputElement | HTMLSelectElement>;
  cellKey: string;
  onChange: (text: string) => void;
  onKeyDown: (event: React.KeyboardEvent) => void;
}) {
  const shared = {
    "aria-label": name,
    "aria-invalid": invalid || undefined,
    "aria-describedby": describedBy,
    onKeyDown,
  };
  const frame = cn(
    "h-8 rounded-md border border-input bg-transparent px-1 text-center tabular-nums outline-none",
    "focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
    "aria-invalid:border-destructive aria-invalid:bg-[var(--color-error-wash)] aria-invalid:text-destructive",
  );
  if (commentOnly) {
    return (
      <select
        {...shared}
        className={cn(frame, "w-24")}
        value={text}
        disabled={locked}
        ref={(el) => {
          if (el) refs.set(cellKey, el);
          else refs.delete(cellKey);
        }}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="" />
        {RESULTS.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      {...shared}
      className={cn(frame, "w-14")}
      inputMode="decimal"
      autoComplete="off"
      value={text}
      readOnly={locked}
      ref={(el) => {
        if (el) refs.set(cellKey, el);
        else refs.delete(cellKey);
      }}
      onFocus={(event) => event.target.select()}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** A quiet button beside a cell that has an entry: its history in a popover. */
function HistoryButton({
  book,
  column,
  student,
  label,
  open,
  onOpenChange,
  changed,
  tabbable,
  returnFocusTo,
}: {
  book: number;
  column: number;
  student: number;
  label: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  changed: boolean;
  tabbable: boolean; // no field to press Alt+H in: the button is the way in
  returnFocusTo: HTMLElement | undefined;
}) {
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          tabIndex={tabbable ? 0 : -1}
          aria-label={`Lịch sử ${label}`}
          title={changed ? "Đã sửa sau khi công bố" : "Lịch sử ô này"}
          className={cn(
            "rounded p-0.5 text-ink-3 hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring",
            changed
              ? "text-destructive"
              : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
          )}
        >
          <History aria-hidden="true" className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-80 text-sm"
        onCloseAutoFocus={(event) => {
          if (!returnFocusTo) return; // no field: the button gets the focus back
          event.preventDefault();
          returnFocusTo.focus();
        }}
      >
        <HistoryList
          book={book}
          column={column}
          student={student}
          label={label}
          changed={changed}
        />
      </PopoverContent>
    </Popover>
  );
}

function HistoryList({
  book,
  column,
  student,
  label,
  changed,
}: {
  book: number;
  column: number;
  student: number;
  label: string;
  changed: boolean;
}) {
  const history = useQuery(cellHistoryQuery(book, column, student));
  return (
    <div className="grid gap-2">
      <p className="font-semibold">Lịch sử: {label}</p>
      {changed && (
        <p className="text-xs italic text-destructive">Đã sửa sau khi công bố cột này.</p>
      )}
      {history.isPending && <p className="italic text-ink-3">Đang tải…</p>}
      {history.isError && (
        <p role="alert" className="text-destructive">
          Không tải được lịch sử.
        </p>
      )}
      <ol className="grid gap-1">
        {history.data?.map((entry) => (
          <li key={entry.id} className="grid grid-cols-[3rem_1fr] gap-2">
            <span className="tabular-nums font-semibold">
              {entry.result ? resultLabel(entry.result) : formatScore(entry.value) || "trống"}
            </span>
            <span className="text-ink-3">
              {entry.entered_by_name}, {stamp(entry.entered_at)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Công bố cột: asks first (a release is once, and a change after it is flagged). */
function ReleaseDialog({
  book,
  column,
  onClose,
}: {
  book: GradebookDetail;
  column: GradebookColumn | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const release = useMutation({
    mutationFn: async (target: GradebookColumn) => {
      const { data, response, error } = await api.POST(
        "/api/setup/gradebooks/{id}/columns/{column}/release/",
        { params: { path: { id: book.id, column: target.id } } },
      );
      if (data) return data;
      const body = error as unknown as { students?: { name: string }[] } | undefined;
      if (response.status === 400 && Array.isArray(body?.students))
        throw new Incomplete(body.students.map((s) => s.name));
      if (response.status === 400)
        throw new Error("Cột này đã được công bố hoặc không còn công bố được.");
      throw new Error(NETWORK);
    },
    onSuccess: () => close(),
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...GRADEBOOK_KEY, book.id] }),
  });
  // Every way out clears the last refusal, so the next column opens clean.
  function close() {
    release.reset();
    onClose();
  }
  const error = release.error;
  const label = column ? columnLabel(column) : "";
  return (
    <Dialog open={column !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Công bố cột {label}?</DialogTitle>
          <DialogDescription>
            Cột chỉ công bố một lần. Sau đó vẫn sửa được điểm, nhưng mỗi lần sửa đều được ghi lại và
            đánh dấu trong sổ.
          </DialogDescription>
        </DialogHeader>
        {error instanceof Incomplete ? (
          <FormError
            message={`Còn ${error.names.length} học sinh chưa có điểm cột ${label}: ${error.names.join(", ")}.`}
          />
        ) : (
          <FormError message={error?.message} />
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={close}>
            Hủy
          </Button>
          <Button disabled={release.isPending} onClick={() => column && release.mutate(column)}>
            Công bố
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The cached grid with the saved cells applied: what the server confirmed, until the refetch. */
function applySaved(
  old: GradebookDetail,
  sent: Record<string, Edit>,
  saved: { column: number; student: number; entry: number | null }[],
  commentOnly: boolean,
): GradebookDetail {
  const byStudent = new Map<number, typeof saved>();
  for (const cell of saved)
    byStudent.set(cell.student, [...(byStudent.get(cell.student) ?? []), cell]);
  const students = old.students.map((student): GradebookRow => {
    const changes = byStudent.get(student.id);
    if (!changes) return student;
    let cells = student.cells;
    for (const { column, entry } of changes) {
      const edit = sent[keyOf(column, student.id)];
      const before = cells.find((c) => c.column === column);
      cells = cells.filter((c) => c.column !== column);
      if (entry === null || !edit) continue;
      const parsed = parseScore(edit.text);
      cells.push({
        column,
        entry,
        value: !commentOnly && parsed.kind === "value" ? parsed.value : null,
        result: commentOnly ? (RESULTS.find((r) => r.value === edit.text)?.value ?? null) : null,
        changed_after_release: before?.changed_after_release ?? false,
      });
    }
    return { ...student, cells };
  });
  return { ...old, students };
}
