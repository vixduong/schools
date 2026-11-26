import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { type ReactNode, useEffect, useState } from "react";
import { leaveChildrenQuery } from "@/api/leave";
import { receivedNoticesQuery } from "@/api/notices";
import { type Child, childDayQuery, childrenQuery, childScoresQuery } from "@/api/portal";
import { LeaveBlock } from "@/components/leave-block";
import { STATUSES } from "@/lib/attendance";
import { columnLabel, formatScore, resultLabel } from "@/lib/grades";
import { sentDay } from "@/lib/notices";
import { hhmm, schoolClock } from "@/lib/timetable";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/guardian")({ component: Screen });

const LOADING = <p className="italic text-ink-3">Đang tải…</p>;

function Failed({ what }: { what: string }) {
  return (
    <p role="alert" className="text-destructive">
      Không tải được {what}. Kiểm tra mạng rồi tải lại trang.
    </p>
  );
}

/** One block of the page: a section head in the display face over its content. */
function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mt-8 grid gap-3">
      <h2 id={id} className="font-serif text-2xl font-light">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** The Guardian view (DESIGN.md, Screens): one column, a child at a time. A student sees the same
 * page for their own record, without Đơn xin nghỉ. */
function Screen() {
  const children = useQuery(childrenQuery);
  const [chosen, setChosen] = useState<number>();
  if (children.isPending) return LOADING;
  if (children.isError) return <Failed what="danh sách học sinh" />;
  const child = children.data.find((c) => c.id === chosen) ?? children.data[0];
  return (
    <section className="mx-auto max-w-[440px]">
      {!child ? (
        <>
          <h1 className="font-serif text-4xl font-light">Học tập</h1>
          <p className="mt-2 italic text-ink-3">Chưa có học sinh nào gắn với tài khoản này.</p>
        </>
      ) : (
        <>
          {children.data.length > 1 && (
            <fieldset className="mb-6 flex flex-wrap items-center gap-2">
              <legend className="sr-only">Chọn học sinh</legend>
              {children.data.map((c) => (
                <label
                  key={c.id}
                  className={cn(
                    "cursor-pointer rounded-full border-[1.5px] border-foreground px-4 py-1.5 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                    c.id === child.id ? "bg-primary text-primary-foreground" : "hover:bg-secondary",
                  )}
                >
                  <input
                    type="radio"
                    className="sr-only"
                    name="child"
                    value={c.id}
                    checked={c.id === child.id}
                    onChange={() => setChosen(c.id)}
                  />
                  {c.name}
                </label>
              ))}
            </fieldset>
          )}
          <h1 className="font-serif text-4xl font-light">{child.name}</h1>
          <p className="mt-1 italic text-ink-3">
            {child.left ? "Đã rời trường" : child.class_name ? `Lớp ${child.class_name}` : ""}
          </p>
          <Today child={child} />
          <Scores child={child} />
          <Leave child={child} />
          <Notices />
        </>
      )}
    </section>
  );
}

/** The clock, refreshed each minute so the current period moves on its own. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Today({ child }: { child: Child }) {
  const day = useQuery(childDayQuery(child.id));
  const clock = schoolClock(useNow());
  return (
    <Block id="today" title="Hôm nay">
      {day.isPending && LOADING}
      {day.isError && <Failed what="các tiết hôm nay" />}
      {day.data?.periods.length === 0 && (
        <p className="italic text-ink-3">Hôm nay không có tiết học nào.</p>
      )}
      {!!day.data?.periods.length && (
        <ol aria-label="Các tiết hôm nay" className="divide-y divide-border">
          {day.data.periods.map((period) => {
            // The School's clock, not the browser's: `on` and the times come from the server.
            const current =
              day.data.on === clock.day &&
              hhmm(period.starts_at) <= clock.time &&
              clock.time < hhmm(period.ends_at);
            const mark = STATUSES.find((s) => s.value === period.status);
            return (
              <li
                key={`${period.session}-${period.number}`}
                aria-current={current ? "time" : undefined}
                className={cn(
                  "grid grid-cols-[6.5rem_1fr] items-baseline gap-x-3 px-2 py-3",
                  current && "bg-[var(--color-select)]",
                )}
              >
                <span className="whitespace-nowrap tabular-nums">
                  {hhmm(period.starts_at)}–{hhmm(period.ends_at)}
                </span>
                <span>
                  <span className="font-semibold">{period.subject_name}</span>
                  <span className="block text-sm text-ink-3">
                    {[period.teacher_name, period.room_name].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <span
                  className={cn(
                    "col-start-2 text-sm",
                    !mark && "italic text-ink-3",
                    mark?.value === "absent_unexcused" && "text-destructive",
                    mark && mark.value !== "present" && "font-semibold",
                  )}
                >
                  {mark?.label ?? "Chưa điểm danh"}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Block>
  );
}

function Scores({ child }: { child: Child }) {
  const scores = useQuery(childScoresQuery(child.id));
  const gradebooks = scores.data?.gradebooks.filter((g) => g.columns.length > 0);
  return (
    <Block id="scores" title="Điểm mới">
      {scores.data?.term_name && <p className="-mt-2 italic text-ink-3">{scores.data.term_name}</p>}
      {scores.isPending && LOADING}
      {scores.isError && <Failed what="điểm" />}
      {gradebooks?.length === 0 && (
        <p className="italic text-ink-3">Chưa có điểm nào được công bố.</p>
      )}
      {!!gradebooks?.length && (
        <ul className="divide-y divide-border">
          {gradebooks.map((gradebook) => (
            <li key={`${gradebook.subject_name}-${gradebook.class_name}`} className="py-3">
              <p className="font-semibold">{gradebook.subject_name}</p>
              <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1 tabular-nums">
                {gradebook.columns.map((cell) => (
                  <div key={`${cell.kind}-${cell.index}`} className="flex gap-1.5">
                    <dt className="text-ink-3">{columnLabel(cell)}</dt>
                    <dd>
                      {formatScore(cell.value) || resultLabel(cell.result) || "–"}
                      {cell.changed_after_release && (
                        <span className="ml-1 text-sm italic text-destructive">đã sửa</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

/** Đơn xin nghỉ only for a child the member may send for: never a student's own view, nor a left
 * child. */
function Leave({ child }: { child: Child }) {
  const leaveChildren = useQuery(leaveChildrenQuery);
  if (!leaveChildren.data?.some((c) => c.id === child.id)) return null;
  return <LeaveBlock student={child} />;
}

function Notices() {
  const notices = useQuery(receivedNoticesQuery);
  return (
    <Block id="notices" title="Thông báo">
      {notices.isPending && LOADING}
      {notices.isError && <Failed what="thông báo" />}
      {notices.data?.length === 0 && <p className="italic text-ink-3">Chưa có thông báo nào.</p>}
      {!!notices.data?.length && (
        <ul className="divide-y divide-border">
          {notices.data.slice(0, 3).map((notice) => (
            <li key={notice.id} className="py-3">
              <p className={cn(!notice.read_at && "font-semibold")}>
                {notice.title}
                {!notice.read_at && <span className="sr-only"> (chưa đọc)</span>}
              </p>
              <p className="text-sm text-ink-3 tabular-nums">
                {notice.sender_name} · {sentDay(notice.sent_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link to="/notices" className="underline underline-offset-4">
          Xem tất cả thông báo
        </Link>
      </p>
    </Block>
  );
}
