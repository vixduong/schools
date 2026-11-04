import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { type Sheet, type Status, sheetQuery } from "@/api/attendance";
import { api } from "@/api/client";
import { myPeriodsQuery } from "@/api/timetable";
import { FormError, formMessage } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { STATUSES, viDate } from "@/lib/attendance";
import { FormFailure, refusal } from "@/lib/messages";
import { hhmm, periodName } from "@/lib/timetable";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/attendance/$entryId/$on")({ component: Screen });

const LEAVE_NOTE = "Có đơn xin nghỉ";
const GENERIC =
  "Không lưu được điểm danh. Danh sách lớp có thể đã thay đổi: tải lại trang rồi điểm danh lại.";

function Screen() {
  const { entryId, on } = Route.useParams();
  const sheet = useQuery(sheetQuery(Number(entryId), on));
  return (
    <section className="grid gap-6">
      <h1 className="font-serif text-4xl font-light">Điểm danh</h1>
      {sheet.isPending && <p className="italic text-ink-3">Đang tải danh sách lớp…</p>}
      {sheet.isError && (
        <p role="alert" className="text-destructive">
          Không mở được bảng điểm danh. Tiết này có thể không diễn ra vào ngày đó, hoặc bạn không có
          quyền xem; kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {sheet.data && <SheetForm key={`${entryId}-${on}`} sheet={sheet.data} />}
    </section>
  );
}

type Row = { status: Status; note: string };

function SheetForm({ sheet }: { sheet: Sheet }) {
  const queryClient = useQueryClient();
  // A period not taken yet starts with everyone present (Có mặt), except a student with an
  // approved leave request (absent with leave, noted); a taken sheet keeps its marks and only
  // shows the "Có đơn" flag, so the teacher can correct a mark taken before the approval.
  const untaken = !sheet.students.some((s) => s.mark);
  const [rows, setRows] = useState<Record<number, Row>>(() =>
    Object.fromEntries(
      sheet.students.map((s) => [
        s.id,
        s.mark
          ? { status: s.mark.status, note: s.mark.note }
          : untaken && s.leave
            ? { status: "absent_excused", note: LEAVE_NOTE }
            : { status: "present", note: "" },
      ]),
    ),
  );
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<string>();
  const change = (id: number, row: Partial<Row>) => {
    setRows((rows) => ({ ...rows, [id]: { ...rows[id], ...row } as Row }));
    setDirty(true);
  };

  const save = useMutation({
    mutationFn: async () => {
      const { data, response, error } = await api.PUT("/api/setup/attendance/{entry}/{on}/", {
        params: { path: { entry: sheet.entry, on: sheet.on } },
        body: {
          marks: sheet.students.map((s) => ({
            student: s.id,
            status: rows[s.id]?.status ?? "present",
            note: rows[s.id]?.note ?? "",
          })),
        },
      });
      // A rule only the database holds (`constraint`) is no invitation problem: say the generic.
      if (!data && response.status === 400 && error && "constraint" in error)
        throw new FormFailure(GENERIC, {});
      if (!data) throw refusal(response.status, error, GENERIC);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(sheetQuery(sheet.entry, sheet.on).queryKey, saved);
      queryClient.invalidateQueries({ queryKey: myPeriodsQuery.queryKey });
      queryClient.invalidateQueries({ queryKey: ["attendance", "class"] });
      setDirty(false);
      setSavedAt(new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }));
    },
  });

  const taken = !untaken;
  let status = "Chưa lưu.";
  if (save.isPending) status = "Đang lưu…";
  else if (dirty) status = "Có thay đổi chưa lưu.";
  else if (savedAt) status = `Đã lưu lúc ${savedAt}.`;
  else if (taken) status = "Đã điểm danh.";

  return (
    <form
      className="grid max-w-3xl gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <p className="italic text-ink-3">
        <span className="font-semibold not-italic text-foreground">{sheet.class_name}</span> ·{" "}
        {sheet.subject_name} · {periodName(sheet)}, {hhmm(sheet.starts_at)}–{hhmm(sheet.ends_at)} ·{" "}
        <span className="tabular-nums">{viDate(sheet.on)}</span>
        {sheet.room_name ? ` · ${sheet.room_name}` : ""}
      </p>
      {!sheet.can_take && <p className="italic text-ink-3">Bạn chỉ xem được bảng điểm danh này.</p>}
      {sheet.students.length === 0 && (
        <p className="italic text-ink-3">Lớp chưa có học sinh nào vào ngày này.</p>
      )}
      <ol className="divide-y divide-border">
        {sheet.students.map((student) => (
          <li
            key={student.id}
            className="grid gap-2 py-3 sm:grid-cols-[minmax(8rem,12rem)_auto_1fr] sm:items-center sm:gap-4"
          >
            <fieldset className="contents">
              <legend className="sr-only">{student.name}</legend>
              <span>
                <span className="font-semibold" aria-hidden="true">
                  {student.name}
                </span>
                {student.leave && <span className="ml-2 text-xs italic text-ink-3">Có đơn</span>}
              </span>
              <div className="flex overflow-hidden rounded-md border-[1.5px] border-foreground">
                {STATUSES.map((option) => {
                  const checked = (rows[student.id]?.status ?? "present") === option.value;
                  return (
                    <label
                      key={option.value}
                      className={cn(
                        "px-3 py-1.5 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-inset has-[:focus-visible]:ring-ring",
                        checked ? "bg-primary text-primary-foreground" : "hover:bg-secondary",
                        sheet.can_take ? "cursor-pointer" : "cursor-not-allowed",
                      )}
                    >
                      <input
                        type="radio"
                        className="sr-only"
                        name={`status-${student.id}`}
                        value={option.value}
                        checked={checked}
                        disabled={!sheet.can_take}
                        onChange={() => change(student.id, { status: option.value })}
                      />
                      {option.label}
                    </label>
                  );
                })}
              </div>
              <Input
                aria-label={`Ghi chú, ${student.name}`}
                placeholder="Ghi chú"
                maxLength={200}
                value={rows[student.id]?.note ?? ""}
                disabled={!sheet.can_take}
                onChange={(event) => change(student.id, { note: event.target.value })}
              />
            </fieldset>
          </li>
        ))}
      </ol>
      <FormError message={formMessage(save.error)} />
      {sheet.can_take && (
        <div className="flex items-center gap-4">
          <Button type="submit" disabled={save.isPending || sheet.students.length === 0}>
            Lưu
          </Button>
          <p role="status" className="text-sm italic text-ink-3">
            {status}
          </p>
        </div>
      )}
    </form>
  );
}
