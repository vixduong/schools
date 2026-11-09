import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import {
  type EmptyCell,
  GRADEBOOK_KEY,
  type GradebookDetail,
  type GradebookStep,
  gradebookQuery,
  type StepAction,
} from "@/api/grades";
import { Field, FormError, fieldError, formMessage } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { LIFECYCLE, STEP_LABEL, stamp, stepFailure } from "@/lib/grades";
import { cn } from "@/lib/utils";

const GENERIC = "Không thực hiện được bước này. Sổ điểm có thể đã đổi: tải lại trang để xem.";

/** The mini lifecycle beside the title: the current state is inked. */
export function LifecycleChips({ status }: { status: GradebookDetail["status"] }) {
  return (
    <ol aria-label="Trạng thái sổ điểm" className="flex gap-2 text-sm">
      {LIFECYCLE.map((chip) => (
        <li
          key={chip.status}
          aria-current={chip.status === status ? "step" : undefined}
          className={cn(
            "rounded-full border-[1.5px] border-foreground px-3 py-0.5",
            chip.status === status ? "bg-foreground text-background" : "text-ink-3",
          )}
        >
          {chip.label}
        </li>
      ))}
    </ol>
  );
}

/** The latest return comment in red ink, with who and when, until the next submit. */
export function ReturnNote({ book }: { book: GradebookDetail }) {
  const step = book.steps.at(-1);
  if (book.return_comment === null || step?.action !== "return") return null;
  return (
    <section
      aria-label="Sổ bị trả lại"
      className="grid gap-1 rounded-md border-[1.5px] border-destructive bg-[var(--color-error-wash)] px-4 py-3 text-destructive"
    >
      <p className="font-semibold">{book.return_comment}</p>
      <p className="text-sm">
        {step.by_name}, {stamp(step.at)}
      </p>
    </section>
  );
}

/** The steps under the grid, oldest first: who, when, and the comment or reason. */
export function StepList({ steps }: { steps: GradebookStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol aria-label="Các bước của sổ" className="grid gap-1 text-sm">
      {steps.map((step) => (
        <li key={`${step.at}-${step.action}`}>
          <span className="font-semibold">{STEP_LABEL[step.action]}</span>
          <span className="text-ink-3">
            {" "}
            · {step.by_name}, {stamp(step.at)}
          </span>
          {step.comment && <span className="block text-destructive">{step.comment}</span>}
        </li>
      ))}
    </ol>
  );
}

/** The submit was refused: these cells are empty. */
class EmptyCells extends Error {
  constructor(readonly cells: EmptyCell[]) {
    super("incomplete");
  }
}

type Ask = {
  title: string;
  description: string;
  confirm: string;
  field?: { label: string; missing: string };
};

/** The steps that ask first; Rút lại để sửa is not among them. */
const ASK: Partial<Record<StepAction, Ask>> = {
  submit: {
    title: "Nộp sổ điểm?",
    description:
      "Sau khi nộp, các ô bị khoá để chờ duyệt. Bạn vẫn rút lại để sửa được cho đến khi sổ được duyệt.",
    confirm: "Nộp sổ",
  },
  approve: {
    title: "Duyệt sổ điểm?",
    description:
      "Duyệt sẽ công bố các cột chưa công bố và khoá sổ. Sau đó chỉ người có quyền mới mở lại được.",
    confirm: "Duyệt",
  },
  return: {
    title: "Trả lại sổ điểm?",
    description: "Sổ quay về trạng thái đang nhập; giáo viên bộ môn thấy lý do này trên sổ.",
    confirm: "Trả lại",
    field: {
      label: "Lý do trả lại",
      missing: "Cần ghi lý do trả lại để giáo viên biết cần sửa gì.",
    },
  },
  reopen: {
    title: "Mở lại sổ điểm?",
    description:
      "Sổ quay về trạng thái đang nhập. Mỗi thay đổi sau khi mở lại đều được ghi lại và đánh dấu trong sổ.",
    confirm: "Mở lại",
    field: { label: "Lý do mở lại", missing: "Cần ghi lý do mở lại." },
  },
};

const BUTTONS: {
  action: StepAction;
  label: string;
  variant: "default" | "secondary" | "destructive";
}[] = [
  { action: "submit", label: "Nộp sổ", variant: "default" },
  { action: "withdraw", label: "Rút lại để sửa", variant: "secondary" },
  { action: "approve", label: "Duyệt", variant: "default" },
  { action: "return", label: "Trả lại", variant: "destructive" },
  { action: "reopen", label: "Mở lại", variant: "destructive" },
];

/** The steps the server says this member may take (`can`), each with its ask-first dialog.
 * `busy`: typed cells are unsaved or a save is in flight, so nothing may be submitted yet.
 * `onIncomplete`: the submit was refused because these cells are empty. */
export function StepActions({
  book,
  busy,
  onIncomplete,
}: {
  book: GradebookDetail;
  busy: boolean;
  onIncomplete: (cells: EmptyCell[]) => void;
}) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState<StepAction | null>(null);
  const [text, setText] = useState("");
  const [missing, setMissing] = useState(false);
  const field = useRef<HTMLInputElement>(null);
  const emptyCells = useRef<EmptyCell[]>([]);

  const step = useMutation({
    mutationFn: async ({ action, typed }: { action: StepAction; typed: string }) => {
      const params = { path: { id: book.id } };
      const { data, response, error } = await (() => {
        switch (action) {
          case "submit":
            return api.POST("/api/setup/gradebooks/{id}/submit/", { params });
          case "withdraw":
            return api.POST("/api/setup/gradebooks/{id}/withdraw/", { params });
          case "approve":
            return api.POST("/api/setup/gradebooks/{id}/approve/", { params });
          case "return":
            return api.POST("/api/setup/gradebooks/{id}/return/", {
              params,
              body: { comment: typed },
            });
          case "reopen":
            return api.POST("/api/setup/gradebooks/{id}/reopen/", {
              params,
              body: { reason: typed },
            });
        }
      })();
      if (data) return data;
      const cells = (error as { cells?: EmptyCell[] } | undefined)?.cells;
      if (response.status === 400 && cells?.length) throw new EmptyCells(cells);
      throw stepFailure(response.status, error, GENERIC);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(gradebookQuery(book.id).queryKey, data);
      close();
    },
    // An incomplete submit closes the dialog; the grid then marks the cells and takes the focus.
    onError: (error) => {
      if (!(error instanceof EmptyCells)) return;
      emptyCells.current = error.cells;
      close();
    },
    // Done or not, the lists are the server's word.
    onSettled: () => queryClient.invalidateQueries({ queryKey: GRADEBOOK_KEY }),
  });

  function close() {
    step.reset();
    setAsking(null);
    setText("");
    setMissing(false);
  }

  function send(action: StepAction) {
    const ask = ASK[action];
    if (ask?.field && !text.trim()) {
      setMissing(true);
      field.current?.focus();
      return;
    }
    step.mutate({ action, typed: text.trim() });
  }

  const ask = asking ? ASK[asking] : undefined;
  const fieldId = "step-text";
  const refused = missing ? ask?.field?.missing : fieldError(step.error, "text");
  const failure = formMessage(step.error);
  const buttons = BUTTONS.filter((b) => book.can.includes(b.action));
  if (buttons.length === 0) return null;
  return (
    <>
      {buttons.map((b) => (
        <Button
          key={b.action}
          variant={b.variant}
          disabled={step.isPending || (b.action === "submit" && busy)}
          title={b.action === "submit" && busy ? "Lưu các ô đã nhập trước khi nộp sổ" : undefined}
          onClick={() => (ASK[b.action] ? setAsking(b.action) : send(b.action))}
        >
          {b.label}
        </Button>
      ))}
      {!ask && <FormError message={failure} />}
      <Dialog open={ask !== undefined} onOpenChange={(open) => !open && close()}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            if (emptyCells.current.length === 0) return;
            event.preventDefault();
            onIncomplete(emptyCells.current);
            emptyCells.current = [];
          }}
        >
          <DialogHeader>
            <DialogTitle>{ask?.title}</DialogTitle>
            <DialogDescription>{ask?.description}</DialogDescription>
          </DialogHeader>
          {ask?.field && (
            <Field id={fieldId} label={ask.field.label} error={refused}>
              <Input
                id={fieldId}
                ref={field}
                maxLength={500}
                value={text}
                onChange={(event) => {
                  setText(event.target.value);
                  setMissing(false);
                }}
                {...(refused
                  ? { "aria-invalid": true, "aria-describedby": `${fieldId}-error` }
                  : {})}
              />
            </Field>
          )}
          <FormError message={failure} />
          <DialogFooter>
            <Button variant="secondary" onClick={close}>
              Hủy
            </Button>
            <Button
              variant={asking === "return" || asking === "reopen" ? "destructive" : "default"}
              disabled={step.isPending}
              onClick={() => asking && send(asking)}
            >
              {ask?.confirm}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
