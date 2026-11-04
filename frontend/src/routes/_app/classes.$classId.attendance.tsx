import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { format } from "date-fns";
import { useState } from "react";
import { classAttendanceQuery } from "@/api/attendance";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DAY_FORMAT, mondayOf, STATUSES, shiftDay, viDate } from "@/lib/attendance";
import { periodName, WEEKDAYS } from "@/lib/timetable";

export const Route = createFileRoute("/_app/classes/$classId/attendance")({ component: Screen });

function Screen() {
  const { classId } = Route.useParams();
  const today = format(new Date(), DAY_FORMAT);
  const thisWeek = mondayOf(today);
  const [week, setWeek] = useState(thisWeek);
  const days = WEEKDAYS.map((weekday, i) => ({ ...weekday, on: shiftDay(week, i) }));
  const lastDay = shiftDay(week, WEEKDAYS.length - 1);
  const overview = useQuery(classAttendanceQuery(Number(classId), week, lastDay));

  return (
    <section className="grid gap-6">
      <div>
        <h1 className="font-serif text-4xl font-light">
          Chuyên cần{overview.data ? ` lớp ${overview.data.class_name}` : ""}
        </h1>
        <p className="mt-2 italic text-ink-3">
          P: vắng có phép · K: vắng không phép · M: muộn. Mỗi ô là các lần vắng hoặc muộn trong
          ngày.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <Button variant="secondary" onClick={() => setWeek(shiftDay(week, -7))}>
          Tuần trước
        </Button>
        <span className="tabular-nums">
          {viDate(week, false)} – {viDate(lastDay, false)}
        </span>
        <Button
          variant="secondary"
          disabled={week >= thisWeek}
          onClick={() => setWeek(shiftDay(week, 7))}
        >
          Tuần sau
        </Button>
      </div>
      {overview.isPending && <p className="italic text-ink-3">Đang tải chuyên cần…</p>}
      {overview.isError && (
        <p role="alert" className="text-destructive">
          Không tải được chuyên cần của lớp. Kiểm tra mạng rồi tải lại trang; nếu vẫn lỗi, bạn có
          thể không có quyền xem lớp này.
        </p>
      )}
      {overview.data?.students.length === 0 && (
        <p className="italic text-ink-3">Lớp chưa có học sinh nào trong tuần này.</p>
      )}
      {!!overview.data?.students.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Học sinh</TableHead>
              {days.map((day) => (
                <TableHead key={day.on}>
                  {day.label}{" "}
                  <span className="tabular-nums font-normal">{viDate(day.on, false)}</span>
                </TableHead>
              ))}
              <TableHead className="text-right">Tổng</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {overview.data.students.map((student) => (
              <TableRow key={student.id}>
                <TableCell className="font-semibold">{student.name}</TableCell>
                {days.map((day) => (
                  <TableCell key={day.on} className="tabular-nums">
                    {student.marks
                      .filter((mark) => mark.on === day.on)
                      .map((mark) => {
                        const status = STATUSES.find((s) => s.value === mark.status);
                        return (
                          <abbr
                            key={`${mark.session}-${mark.number}`}
                            title={`${periodName(mark)} · ${mark.subject_name} · ${status?.label}`}
                            className="mr-1 no-underline"
                          >
                            {status?.code}
                          </abbr>
                        );
                      })}
                  </TableCell>
                ))}
                <TableCell className="text-right tabular-nums">{student.marks.length}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
