import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { myPeriodsQuery } from "@/api/timetable";
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
  const now = useNow();
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Hôm nay</h1>
      {periods.isPending && <p className="mt-2 italic text-ink-3">Đang tải các tiết hôm nay…</p>}
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
                  "grid grid-cols-[6.5rem_1fr_auto] items-baseline gap-x-4 px-2 py-3",
                  current && "bg-[var(--color-select)]",
                )}
              >
                <span className="tabular-nums">
                  {hhmm(period.starts_at)}–{hhmm(period.ends_at)}
                </span>
                <span>
                  <span className="font-semibold">{period.class_name}</span>
                  <span className="text-ink-3"> · {period.subject_name}</span>
                </span>
                <span className="text-sm text-ink-3">{period.room_name ?? ""}</span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
