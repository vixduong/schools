import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import {
  GRADEBOOK_KEY,
  type GradebookDetail,
  type GradebookRow,
  gradebookQuery,
} from "@/api/grades";
import { Field, FormError, formMessage } from "@/components/auth-page";
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
import {
  carriedFailure,
  carriedLabel,
  formatScore,
  MAX_DOCUMENT_MB,
  parseScore,
  RESULTS,
} from "@/lib/grades";
import { FormFailure } from "@/lib/messages";

type Carried = GradebookRow["carried"][number];
const keyOf = (c: { kind: string; index: number }) => `${c.kind}:${c.index}`;

/** The homeroom teacher records an arriving student's source School, transfer document and the
 * results brought for this gradebook's subject and term (one field per column of the grid). */
export function TransferDialog({
  book,
  student,
  onClose,
}: {
  book: GradebookDetail;
  student: GradebookRow;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const commentOnly = book.assessment === "comment_only";
  const current = new Map<string, Carried>(student.carried.map((c) => [keyOf(c), c]));
  // A year average exists only in a semester 2 book of a two-term year; a scored one needs the
  // first semester's figure from the previous School.
  const year = student.averages.year;
  const fields: Pick<Carried, "kind" | "index">[] =
    !commentOnly && year && year.reason !== "terms"
      ? [...book.columns, { kind: "previous_semester_average", index: 1 }]
      : book.columns;
  const textOf = (c: Carried | undefined) =>
    commentOnly ? (c?.result ?? "") : formatScore(c?.value);
  const [source, setSource] = useState(student.arrival?.source_school ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [texts, setTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((c) => [keyOf(c), textOf(current.get(keyOf(c)))])),
  );
  // A record the dialog itself made counts at once: a retry after the results were refused must
  // not send the file again.
  const recorded = useRef(false);
  const hasRecord = student.arrival?.document_name != null || recorded.current;
  const locked = book.status !== "draft";

  const save = useMutation({
    mutationFn: async () => {
      if (!source.trim() && (file || !hasRecord))
        throw new FormFailure(undefined, { source_school: "Cần ghi trường cũ." });
      if (!file && !hasRecord)
        throw new FormFailure(undefined, { document: "Cần tải hồ sơ chuyển." });
      // The school and the file are one record: a new school needs its document sent again.
      if (!file && source.trim() !== (student.arrival?.source_school ?? source.trim()))
        throw new FormFailure(undefined, {
          document: "Đổi trường cũ thì cần tải lại hồ sơ chuyển.",
        });
      const path = { id: book.id, student: student.id };
      if (file) {
        const sent = await api.POST("/api/setup/gradebooks/{id}/students/{student}/transfer/", {
          params: { path },
          // The document is a File, which the generated type (a URI string) cannot say.
          body: { source_school: source.trim(), document: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.set("source_school", body.source_school);
            form.set("document", body.document as unknown as Blob);
            return form;
          },
        });
        if (!sent.data) throw carriedFailure(sent.response.status, sent.error);
        recorded.current = true;
        setFile(null);
      }
      const results = [];
      for (const column of fields) {
        const key = keyOf(column);
        const text = texts[key] ?? "";
        const before = textOf(current.get(key));
        if (text === before) continue;
        if (commentOnly) {
          results.push({
            kind: column.kind,
            index: column.index,
            value: null,
            result: RESULTS.find((r) => r.value === text)?.value ?? null,
          });
          continue;
        }
        const parsed = parseScore(text);
        if (parsed.kind === "invalid")
          throw new FormFailure(undefined, { [key]: "Chưa phải số điểm." });
        results.push({
          kind: column.kind,
          index: column.index,
          value: parsed.kind === "value" ? parsed.value : null,
          result: null,
        });
      }
      const put = results.length
        ? await api.PUT("/api/setup/gradebooks/{id}/students/{student}/carried/", {
            params: { path },
            body: { results },
          })
        : undefined;
      if (put && !put.data) throw carriedFailure(put.response.status, put.error);
      return (
        put?.data ?? (await queryClient.fetchQuery({ ...gradebookQuery(book.id), staleTime: 0 }))
      );
    },
    onSuccess: (data) => {
      queryClient.setQueryData(gradebookQuery(book.id).queryKey, data);
      onClose();
    },
    // Done or not, the lists are the server's word.
    onSettled: () => queryClient.invalidateQueries({ queryKey: GRADEBOOK_KEY }),
  });

  const fieldError = (name: string) =>
    save.error instanceof FormFailure ? save.error.fields[name] : undefined;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Kết quả mang sang: {student.name}</DialogTitle>
            <DialogDescription>
              Điểm {book.subject_name} {book.term_name} học sinh mang từ trường cũ, kèm hồ sơ
              chuyển. Chúng nằm riêng, không thay điểm của trường.
            </DialogDescription>
          </DialogHeader>
          {locked && <p className="italic text-destructive">Sổ đã nộp, không sửa được.</p>}
          <Field id="source" label="Trường cũ" error={fieldError("source_school")}>
            <Input
              id="source"
              value={source}
              maxLength={200}
              onChange={(event) => setSource(event.target.value)}
              aria-invalid={!!fieldError("source_school") || undefined}
            />
          </Field>
          <Field id="document" label="Hồ sơ chuyển" error={fieldError("document")}>
            <Input
              id="document"
              type="file"
              accept="application/pdf,image/jpeg,image/png"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              aria-invalid={!!fieldError("document") || undefined}
            />
            <p className="text-xs text-ink-3">
              {hasRecord
                ? `Đang có: ${student.arrival?.document_name}. Chọn tệp mới để thay.`
                : "Chưa có hồ sơ."}{" "}
              PDF, JPEG hoặc PNG, tối đa {MAX_DOCUMENT_MB} MB.
            </p>
          </Field>
          <fieldset className="grid gap-2">
            <legend className="text-sm font-semibold">Điểm đã có ở trường cũ</legend>
            <div className="flex flex-wrap gap-3">
              {fields.map((column) => {
                const key = keyOf(column);
                const id = `carried-${key}`;
                return (
                  <div key={key} className="grid gap-1">
                    <label htmlFor={id} className="text-xs font-semibold">
                      {carriedLabel(column)}
                    </label>
                    {commentOnly ? (
                      <select
                        id={id}
                        className="h-8 w-24 rounded-md border border-input bg-transparent px-1"
                        value={texts[key] ?? ""}
                        onChange={(event) => setTexts({ ...texts, [key]: event.target.value })}
                      >
                        <option value="" />
                        {RESULTS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        id={id}
                        className="h-8 w-16 text-center tabular-nums"
                        inputMode="decimal"
                        autoComplete="off"
                        value={texts[key] ?? ""}
                        aria-invalid={!!fieldError(key) || undefined}
                        onChange={(event) => setTexts({ ...texts, [key]: event.target.value })}
                      />
                    )}
                    {fieldError(key) && (
                      <p className="text-xs text-destructive">{fieldError(key)}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </fieldset>
          <FormError message={formMessage(save.error)} />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              Đóng
            </Button>
            <Button type="submit" disabled={save.isPending || locked}>
              Lưu
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
