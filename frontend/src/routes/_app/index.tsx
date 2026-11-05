import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { meQuery } from "@/api/queries";
import { myPeriodsQuery } from "@/api/timetable";
import { LeaveInbox } from "@/components/leave-inbox";
import { TeacherBoard } from "@/components/teacher-board";
import { Button } from "@/components/ui/button";
import { resultLabel } from "@/lib/attendance";
import { reach } from "@/lib/capabilities";
import { hhmm, isCurrent } from "@/lib/timetable";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/")({ component: Screen });

/** The clock, refreshed each minute so the current period moves on its own. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Screen() {
  const periods = useQuery(myPeriodsQuery);
  const me = useQuery(meQuery);
  const now = useNow();
  const today = now.toLocaleDateString("sv"); // yyyy-mm-dd, local
  const decidesLeave = !!me.data && reach(me.data, "leave_request.approve") === "write";
  const entersScores = !!me.data && reach(me.data, "scores.enter") === "write";
  const homerooms = me.data?.role_assignments.filter((r) => r.role === "homeroom_teacher") ?? [];
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Hôm nay</h1>
      <div
        className={cn(
          decidesLeave && "mt-4 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]",
        )}
      >
        <div>
          {periods.isPending && (
            <p className="mt-2 italic text-ink-3">Đang tải các tiết hôm nay…</p>
          )}
          {periods.isError && (
            <p role="alert" className="mt-2 text-destructive">
              Không tải được các tiết hôm nay. Kiểm tra mạng rồi tải lại trang.
            </p>
          )}
          {periods.data?.length === 0 && (
            <p className="mt-2 italic text-ink-3">Hôm nay bạn không có tiết nào.</p>
          )}
          {!!periods.data?.length && (
            <ol aria-label="Các tiết hôm nay" className="mt-4 max-w-xl divide-y divide-border">
              {periods.data.map((period) => {
                const current = isCurrent(period, now);
                return (
                  <li
                    key={period.id}
                    aria-current={current ? "time" : undefined}
                    className={cn(
                      "grid grid-cols-[6.5rem_1fr_auto] items-center gap-x-4 px-2 py-3",
                      current && "bg-[var(--color-select)]",
                    )}
                  >
                    <span className="tabular-nums">
                      {hhmm(period.starts_at)}–{hhmm(period.ends_at)}
                    </span>
                    <span>
                      <span className="font-semibold">{period.class_name}</span>
                      <span className="text-ink-3"> · {period.subject_name}</span>
                      <span className="block text-sm text-ink-3">
                        {resultLabel(period.attendance)}
                      </span>
                    </span>
                    <span className="flex items-center gap-4 text-sm text-ink-3">
                      {period.room_name ?? ""}
                      <Button asChild variant={current ? "default" : "quiet"}>
                        <Link
                          to="/attendance/$entryId/$on"
                          params={{ entryId: String(period.id), on: today }}
                        >
                          Điểm danh
                        </Link>
                      </Button>
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          {homerooms.map((role) => (
            <p key={role.id} className="mt-6">
              <Link
                to="/classes/$classId/attendance"
                params={{ classId: String(role.school_class) }}
                className="underline underline-offset-4"
              >
                Chuyên cần lớp chủ nhiệm
              </Link>
            </p>
          ))}
        </div>
        {decidesLeave && <LeaveInbox />}
      </div>
      {entersScores && <TeacherBoard />}
    </section>
  );
}
