import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { type BellPeriod, classTimetableQuery, type TimetableEntry } from "@/api/timetable";
import {
  Field,
  FormError,
  fieldError,
  formMessage,
  invalidProps,
  useFocusRefused,
} from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { FormFailure, refusal } from "@/lib/messages";
import { hhmm, inSchoolOrder, periodName, WEEKDAYS } from "@/lib/timetable";

type Subject = components["schemas"]["Subject"];
type Room = components["schemas"]["Room"];
type Assignment = components["schemas"]["RoleAssignmentSetup"];
type Person = components["schemas"]["Membership"];

/** One cell of the draft: ids as the `<select>`s hold them ("" for none). */
type Cell = { subject: string; teacher: string; room: string };
const EMPTY: Cell = { subject: "", teacher: "", room: "" };
const keyOf = (weekday: number, bellPeriod: number) => `${weekday}-${bellPeriod}`;

const GENERIC = "Không lưu được thời khóa biểu. Kiểm tra mạng rồi thử lại.";
const FROM_DATE: Record<string, string> = {
  not_after_today: "Ngày áp dụng phải sau hôm nay.",
  outside_school_year: "Ngày áp dụng phải nằm trong năm học của lớp.",
};
const CLASH_WHAT: Record<string, string> = {
  timetableentry_class_clash: "Lớp",
  timetableentry_teacher_clash: "Giáo viên",
  timetableentry_room_clash: "Phòng",
};

type Clash = {
  weekday: number;
  bell_period: number;
  class: number;
  subject: number;
  teacher: number;
  room: number | null;
};

/** The 400 of a replace in Vietnamese: a clash names the other entry; other refusals read plain. */
function replaceFailure(
  status: number,
  body: unknown,
  name: (kind: "class" | "subject" | "teacher" | "room" | "slot", id: number) => string,
) {
  const error = body as { constraint?: string[]; clash?: Clash; valid_from?: string[] } | undefined;
  const constraint = error?.constraint?.[0];
  if (status === 400 && constraint && constraint in CLASH_WHAT) {
    const c = error?.clash;
    const slot = c ? `${WEEKDAYS[c.weekday - 1]?.label ?? ""}, ${name("slot", c.bell_period)}` : "";
    return new FormFailure(
      c
        ? `${CLASH_WHAT[constraint]} đã có tiết vào ${slot}: lớp ${name("class", c.class)}, môn ${name("subject", c.subject)}, ${name("teacher", c.teacher)}${c.room ? `, phòng ${name("room", c.room)}` : ""}.`
        : `${CLASH_WHAT[constraint]} bị trùng tiết trong tuần này.`,
      {},
    );
  }
  if (status === 400 && constraint === "timetableentry_teacher_teaches")
    return new FormFailure("Giáo viên chưa được phân công dạy môn này ở lớp này.", {});
  const code = error?.valid_from?.[0];
  if (status === 400 && code && FROM_DATE[code])
    return new FormFailure(undefined, { valid_from: FROM_DATE[code] });
  return refusal(status, body, GENERIC);
}

/** The earliest day a replacement can start: a new week never rewrites today's periods. */
function tomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The week of one class: bell periods as rows, Thứ 2 to Thứ 7 as columns; each cell picks a
 * subject, then a teacher who teaches it in this class, then a room. `entries` are the ones in
 * force today; the grid is applied from "Áp dụng từ ngày". */
export function TimetableGrid({
  schoolClass,
  className,
  periods,
  entries,
  subjects,
  rooms,
  assignments,
  people,
  classNames,
  canEdit,
}: {
  schoolClass: number;
  className: string;
  periods: BellPeriod[];
  entries: TimetableEntry[];
  subjects: Subject[];
  rooms: Room[];
  assignments: Assignment[];
  people: Person[];
  classNames: Map<number, string>;
  canEdit: boolean;
}) {
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const [draft, setDraft] = useState<Record<string, Cell>>(() =>
    Object.fromEntries(
      entries.map((e) => [
        keyOf(e.weekday, e.bell_period),
        {
          subject: String(e.subject),
          teacher: String(e.teacher),
          room: e.room ? String(e.room) : "",
        },
      ]),
    ),
  );
  const [incomplete, setIncomplete] = useState(false);
  const [from, setFrom] = useState(tomorrow);

  const personName = (id: number) => people.find((p) => p.id === id)?.display_name ?? `#${id}`;
  const names = (kind: "class" | "subject" | "teacher" | "room" | "slot", id: number) => {
    switch (kind) {
      case "class":
        return classNames.get(id) ?? `#${id}`;
      case "subject":
        return subjects.find((s) => s.id === id)?.name ?? `#${id}`;
      case "teacher":
        return personName(id);
      case "room":
        return rooms.find((r) => r.id === id)?.name ?? `#${id}`;
      case "slot": {
        const period = periods.find((p) => p.id === id);
        return period ? periodName(period) : `#${id}`;
      }
    }
  };

  /** Active members who hold a subject-teacher role for this subject in this class on the day
   * the grid applies from. */
  const teachersOf = (subject: string) => {
    const ids = new Set(
      assignments
        .filter(
          (a) =>
            a.role === "subject_teacher" &&
            a.status === "active" &&
            a.school_class === schoolClass &&
            String(a.subject) === subject &&
            a.valid_from <= from &&
            (!a.valid_to || a.valid_to >= from),
        )
        .map((a) => a.membership),
    );
    return people.filter((p) => p.status === "active" && ids.has(p.id));
  };

  const save = useMutation({
    mutationFn: async (validFrom: string) => {
      const slots = Object.entries(draft).filter(([, cell]) => cell.subject || cell.teacher);
      if (slots.some(([, cell]) => !cell.subject || !cell.teacher)) {
        setIncomplete(true);
        throw new FormFailure("Chọn cả môn và giáo viên cho mỗi ô đã điền.", {});
      }
      setIncomplete(false);
      const { response, error } = await api.POST("/api/setup/classes/{id}/timetable/", {
        params: { path: { id: schoolClass } },
        body: {
          valid_from: validFrom,
          entries: slots.map(([key, cell]) => {
            const [weekday = 0, bellPeriod = 0] = key.split("-").map(Number);
            return {
              weekday,
              bell_period: bellPeriod,
              subject: Number(cell.subject),
              teacher: Number(cell.teacher),
              room: cell.room ? Number(cell.room) : null,
            };
          }),
        },
      });
      if (!response.ok) throw replaceFailure(response.status, error, names);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: classTimetableQuery(schoolClass).queryKey }),
  });
  useFocusRefused(form, save.error);

  function change(key: string, patch: Partial<Cell>) {
    setDraft((d) => ({ ...d, [key]: { ...(d[key] ?? EMPTY), ...patch } }));
  }

  if (periods.length === 0)
    return (
      <p className="italic text-ink-3">
        Chưa có tiết nào để xếp. Thêm các tiết ở bảng giờ học phía trên.
      </p>
    );

  return (
    <form
      ref={form}
      aria-label={`Thời khóa biểu lớp ${className}`}
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(from);
      }}
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[60rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th scope="col" className="w-24 p-2 font-semibold">
                Tiết
              </th>
              {WEEKDAYS.map((day) => (
                <th key={day.number} scope="col" className="p-2 font-semibold">
                  {day.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {inSchoolOrder(periods).map((period) => (
              <tr key={period.id} className="border-b border-border align-top">
                <th scope="row" className="p-2 text-left font-normal">
                  <span className="font-semibold">{periodName(period)}</span>
                  <br />
                  <span className="tabular-nums text-ink-3">
                    {hhmm(period.starts_at)}–{hhmm(period.ends_at)}
                  </span>
                </th>
                {WEEKDAYS.map((day) => {
                  const key = keyOf(day.number, period.id);
                  const cell = draft[key] ?? EMPTY;
                  const label = `${day.label}, ${periodName(period)}`;
                  const teachers = cell.subject ? teachersOf(cell.subject) : [];
                  return (
                    <td key={day.number} className="grid gap-1 p-1">
                      <NativeSelect
                        aria-label={`Môn, ${label}`}
                        value={cell.subject}
                        disabled={!canEdit}
                        aria-invalid={
                          incomplete && !cell.subject && cell.teacher ? true : undefined
                        }
                        onChange={(e) => change(key, { subject: e.target.value, teacher: "" })}
                      >
                        <option value="">Môn</option>
                        {subjects
                          .filter((s) => s.is_active || String(s.id) === cell.subject)
                          .map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                      </NativeSelect>
                      <NativeSelect
                        aria-label={`Giáo viên, ${label}`}
                        value={cell.teacher}
                        disabled={!canEdit || !cell.subject}
                        aria-invalid={
                          incomplete && cell.subject && !cell.teacher ? true : undefined
                        }
                        onChange={(e) => change(key, { teacher: e.target.value })}
                      >
                        <option value="">Giáo viên</option>
                        {teachers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.display_name}
                          </option>
                        ))}
                        {cell.teacher && !teachers.some((p) => String(p.id) === cell.teacher) && (
                          <option value={cell.teacher}>{personName(Number(cell.teacher))}</option>
                        )}
                      </NativeSelect>
                      <NativeSelect
                        aria-label={`Phòng, ${label}`}
                        value={cell.room}
                        disabled={!canEdit}
                        onChange={(e) => change(key, { room: e.target.value })}
                      >
                        <option value="">Phòng</option>
                        {rooms
                          .filter((r) => r.is_active || String(r.id) === cell.room)
                          .map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.name}
                            </option>
                          ))}
                      </NativeSelect>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canEdit && (
        <div className="grid max-w-sm gap-4">
          <Field
            id="valid_from"
            label="Áp dụng từ ngày"
            error={fieldError(save.error, "valid_from")}
          >
            <Input
              id="valid_from"
              name="valid_from"
              type="date"
              lang="vi"
              required
              min={tomorrow()}
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              {...invalidProps(save.error, "valid_from")}
            />
          </Field>
          <FormError message={formMessage(save.error)} />
          {save.isSuccess && <p role="status">Đã lưu thời khóa biểu.</p>}
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Đang lưu…" : "Lưu"}
          </Button>
        </div>
      )}
    </form>
  );
}
