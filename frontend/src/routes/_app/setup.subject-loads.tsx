import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/api/client";
import { type Grade, gradesQuery, type SubjectLoad, subjectLoadsQuery } from "@/api/grades";
import { meQuery } from "@/api/queries";
import { subjectsQuery, yearsQuery } from "@/api/timetable";
import { Field, FormError } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { reach } from "@/lib/capabilities";
import { NETWORK } from "@/lib/messages";

export const Route = createFileRoute("/_app/setup/subject-loads")({ component: Screen });

const REFUSED: Record<string, string> = {
  subjectload_frozen_by_gradebooks: "Đã có sổ điểm dùng số tiết này nên không đổi được.",
  subjectload_periods_in_1_to_400: "Số tiết một năm từ 1 đến 400.",
};

function Screen() {
  const { data: me } = useSuspenseQuery(meQuery);
  const access = reach(me, "school.configure");
  if (!access) {
    return (
      <section>
        <h1 className="font-serif text-4xl font-light">Số tiết các môn</h1>
        <p className="mt-2 italic text-ink-3">Bạn không có quyền xem số tiết của trường.</p>
      </section>
    );
  }
  return <Loads canEdit={access === "write"} />;
}

function Loads({ canEdit }: { canEdit: boolean }) {
  const years = useQuery(yearsQuery);
  const grades = useQuery(gradesQuery);
  const subjects = useQuery(subjectsQuery);
  const [picked, setPicked] = useState<number>();
  const today = new Date().toLocaleDateString("sv");
  const year =
    picked ??
    (years.data?.find((y) => y.starts_on <= today && today <= y.ends_on) ?? years.data?.at(-1))?.id;
  const loads = useQuery({ ...subjectLoadsQuery(year ?? 0), enabled: year !== undefined });
  const failed = [years, grades, subjects, loads].some((q) => q.isError);
  const active = subjects.data?.filter((s) => s.is_active) ?? [];
  return (
    <section className="grid gap-8">
      <div>
        <h1 className="font-serif text-4xl font-light">Số tiết các môn</h1>
        <p className="mt-2 italic text-ink-3">
          Số tiết một năm của mỗi môn theo khối quyết định số cột điểm thường xuyên của sổ điểm.
          {canEdit
            ? " Không đổi được khi đã có sổ điểm của năm học, khối và môn đó."
            : " Chỉ để xem."}
        </p>
      </div>
      {failed && (
        <p role="alert" className="text-destructive">
          Không tải được dữ liệu. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {year !== undefined && (
        <Field id="school-year" label="Năm học">
          <NativeSelect
            id="school-year"
            value={year}
            onChange={(e) => setPicked(Number(e.target.value))}
          >
            {years.data?.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
      )}
      {years.data?.length === 0 && <p className="italic text-ink-3">Chưa có năm học nào.</p>}
      {year !== undefined &&
        loads.data &&
        [...(grades.data ?? [])]
          .sort((a, b) => a.number - b.number)
          .map((grade) => (
            <GradeTable
              key={`${year}-${grade.id}`}
              year={year}
              grade={grade}
              subjects={active}
              loads={loads.data.filter((l) => l.grade === grade.id)}
              canEdit={canEdit}
            />
          ))}
      {active.length === 0 && subjects.data && (
        <p className="italic text-ink-3">Chưa có môn học nào.</p>
      )}
    </section>
  );
}

function GradeTable({
  year,
  grade,
  subjects,
  loads,
  canEdit,
}: {
  year: number;
  grade: Grade;
  subjects: { id: number; name: string }[];
  loads: SubjectLoad[];
  canEdit: boolean;
}) {
  return (
    <div className="grid max-w-xl gap-2">
      <h2 className="font-serif text-2xl font-light">Khối {grade.number}</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="px-2 py-2 text-left font-semibold">
              Môn
            </th>
            <th scope="col" className="px-2 py-2 text-left font-semibold">
              Số tiết một năm
            </th>
          </tr>
        </thead>
        <tbody>
          {subjects.map((subject) => (
            <LoadRow
              key={subject.id}
              year={year}
              grade={grade}
              subject={subject}
              load={loads.find((l) => l.subject === subject.id)}
              canEdit={canEdit}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoadRow({
  year,
  grade,
  subject,
  load,
  canEdit,
}: {
  year: number;
  grade: Grade;
  subject: { id: number; name: string };
  load: SubjectLoad | undefined;
  canEdit: boolean;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(load ? String(load.periods_per_year) : "");
  const save = useMutation({
    mutationFn: async () => {
      const periods = Number(text);
      const body = { periods_per_year: periods };
      const { data, response, error } = load
        ? await api.PATCH("/api/setup/subject-loads/{id}/", {
            params: { path: { id: load.id } },
            body,
          })
        : await api.POST("/api/setup/subject-loads/", {
            // `id` is read-only: the schema keeps it in the request type, the server ignores it.
            body: {
              school_year: year,
              grade: grade.id,
              subject: subject.id,
              ...body,
            } as SubjectLoad,
          });
      if (data) return data;
      if (response.status === 400) {
        const names = ((error as { constraint?: string[] } | undefined)?.constraint ??
          []) as string[];
        throw new Error(REFUSED[names[0] ?? ""] ?? "Không lưu được số tiết này.");
      }
      throw new Error(NETWORK);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: subjectLoadsQuery(year).queryKey }),
  });
  const changed = text !== (load ? String(load.periods_per_year) : "");
  const id = `periods-${grade.id}-${subject.id}`;
  return (
    <tr className="border-b border-border">
      <th scope="row" className="px-2 py-1 text-left font-normal">
        <label htmlFor={id}>{subject.name}</label>
      </th>
      <td className="px-2 py-1">
        <div className="flex items-center gap-3">
          <Input
            id={id}
            inputMode="numeric"
            className="h-8 w-20 text-right tabular-nums"
            value={text}
            disabled={!canEdit}
            aria-invalid={save.isError || undefined}
            onChange={(event) => {
              setText(event.target.value);
              save.reset();
            }}
          />
          {canEdit && (
            <Button
              variant="quiet"
              disabled={!changed || !/^\d+$/.test(text) || save.isPending}
              onClick={() => save.mutate()}
              aria-label={`Lưu số tiết ${subject.name}, khối ${grade.number}`}
            >
              Lưu
            </Button>
          )}
          {save.isSuccess && !changed && <span className="text-xs italic text-ink-3">Đã lưu</span>}
        </div>
        <FormError message={save.error?.message} />
      </td>
    </tr>
  );
}
