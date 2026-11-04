import { addDays, format, startOfWeek } from "date-fns";
import type { Status } from "@/api/attendance";
import type { MyPeriod } from "@/api/timetable";

export const STATUSES: { value: Status; label: string; code?: string }[] = [
  { value: "present", label: "Có mặt" },
  { value: "late", label: "Muộn", code: "M" },
  { value: "absent_excused", label: "Vắng có phép", code: "P" },
  { value: "absent_unexcused", label: "Vắng không phép", code: "K" },
];

export const DAY_FORMAT = "yyyy-MM-dd";

/** What a period's attendance reads on the teacher's home. */
export function resultLabel(attendance: MyPeriod["attendance"] | undefined): string {
  if (!attendance) return "Chưa điểm danh";
  const parts = [
    attendance.absent > 0 ? `Vắng ${attendance.absent}` : "",
    attendance.late > 0 ? `Muộn ${attendance.late}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Đủ";
}

/** The Monday of the week holding `day` (yyyy-mm-dd). */
export function mondayOf(day: string): string {
  return format(startOfWeek(new Date(`${day}T00:00:00`), { weekStartsOn: 1 }), DAY_FORMAT);
}

export function shiftDay(day: string, days: number): string {
  return format(addDays(new Date(`${day}T00:00:00`), days), DAY_FORMAT);
}

/** "2026-11-04" to "04/11/2026" (dd/mm/yyyy, DESIGN.md). */
export function viDate(day: string, withYear = true): string {
  const [year, month, date] = day.split("-");
  return withYear ? `${date}/${month}/${year}` : `${date}/${month}`;
}
