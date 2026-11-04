import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { meQuery } from "@/api/queries";
import {
  bellPeriodsQuery,
  classesQuery,
  classTimetableQuery,
  membershipsQuery,
  roleAssignmentsQuery,
  roomsQuery,
  subjectsQuery,
  yearsQuery,
} from "@/api/timetable";
import { Field } from "@/components/auth-page";
import { BellSchedule } from "@/components/bell-schedule";
import { TimetableGrid } from "@/components/timetable-grid";
import { NativeSelect } from "@/components/ui/native-select";
import { reach } from "@/lib/capabilities";

export const Route = createFileRoute("/_app/timetable")({ component: Screen });

function Screen() {
  const { data: me } = useSuspenseQuery(meQuery);
  const access = reach(me, "school.configure");
  if (!access) {
    return (
      <section>
        <h1 className="font-serif text-4xl font-light">Thời khóa biểu</h1>
        <p className="mt-2 italic text-ink-3">Bạn không có quyền xem thời khóa biểu của trường.</p>
      </section>
    );
  }
  return <Timetable canEdit={access === "write"} />;
}

function Timetable({ canEdit }: { canEdit: boolean }) {
  const years = useQuery(yearsQuery);
  const classes = useQuery(classesQuery);
  const subjects = useQuery(subjectsQuery);
  const rooms = useQuery(roomsQuery);
  const assignments = useQuery(roleAssignmentsQuery);
  const people = useQuery(membershipsQuery);

  const [pickedYear, setPickedYear] = useState<number>();
  const [pickedClass, setPickedClass] = useState<number>();
  const today = new Date().toLocaleDateString("sv"); // yyyy-mm-dd, local
  const year =
    pickedYear ??
    (years.data?.find((y) => y.starts_on <= today && today <= y.ends_on) ?? years.data?.at(-1))?.id;
  const yearClasses = classes.data?.filter((c) => c.school_year === year) ?? [];
  const schoolClass = yearClasses.some((c) => c.id === pickedClass)
    ? pickedClass
    : yearClasses[0]?.id;

  const periods = useQuery({ ...bellPeriodsQuery(year ?? 0), enabled: year !== undefined });
  const entries = useQuery({
    ...classTimetableQuery(schoolClass ?? 0),
    enabled: schoolClass !== undefined,
  });

  const loading = [years, classes, subjects, rooms, assignments, people].some((q) => q.isPending);
  const failed = [years, classes, subjects, rooms, assignments, people].some((q) => q.isError);

  return (
    <section className="grid gap-8">
      <div>
        <h1 className="font-serif text-4xl font-light">Thời khóa biểu</h1>
        <p className="mt-2 italic text-ink-3">
          {canEdit
            ? "Xếp một tuần cho mỗi lớp rồi áp dụng từ một ngày; tuần cũ vẫn được giữ."
            : "Thời khóa biểu của các lớp, chỉ để xem."}
        </p>
      </div>
      {failed && (
        <p role="alert" className="text-destructive">
          Không tải được dữ liệu. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {loading && !failed && <p className="italic text-ink-3">Đang tải…</p>}
      {years.data?.length === 0 && (
        <p className="italic text-ink-3">Chưa có năm học nào. Tạo năm học trước khi xếp lịch.</p>
      )}
      {year !== undefined && (
        <>
          <div className="flex flex-wrap gap-4">
            <Field id="school-year" label="Năm học">
              <NativeSelect
                id="school-year"
                value={year}
                onChange={(e) => setPickedYear(Number(e.target.value))}
              >
                {years.data?.map((y) => (
                  <option key={y.id} value={y.id}>
                    {y.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="school-class" label="Lớp">
              <NativeSelect
                id="school-class"
                value={schoolClass ?? ""}
                disabled={yearClasses.length === 0}
                onChange={(e) => setPickedClass(Number(e.target.value))}
              >
                {yearClasses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          {periods.data && (
            <BellSchedule periods={periods.data} schoolYear={year} canEdit={canEdit} />
          )}
          {yearClasses.length === 0 && classes.data && (
            <p className="italic text-ink-3">Năm học này chưa có lớp nào.</p>
          )}
          {schoolClass !== undefined &&
            periods.data &&
            entries.data &&
            subjects.data &&
            rooms.data &&
            assignments.data &&
            people.data && (
              <TimetableGrid
                key={schoolClass}
                schoolClass={schoolClass}
                className={yearClasses.find((c) => c.id === schoolClass)?.name ?? ""}
                periods={periods.data}
                entries={entries.data}
                subjects={subjects.data}
                rooms={rooms.data}
                assignments={assignments.data}
                people={people.data}
                classNames={new Map(classes.data?.map((c) => [c.id, c.name]))}
                canEdit={canEdit}
              />
            )}
        </>
      )}
    </section>
  );
}
