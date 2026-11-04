import type { LeaveRequest } from "@/api/leave";
import type { Pin } from "@/components/ticket";
import { viDate } from "@/lib/attendance";

/** The state word of a request and the pin beside it (DESIGN.md: gold waits, ink is decided,
 * red needs a person or was refused). */
export const LEAVE_STATES: Record<LeaveRequest["status"], { label: string; pin: Pin }> = {
  waiting: { label: "Đang chờ", pin: "waiting" },
  approved: { label: "Đã duyệt", pin: "open" },
  declined: { label: "Từ chối", pin: "alert" },
  cancelled: { label: "Đã huỷ", pin: "locked" },
};

/** "04/11/2026" for one day, "04/11/2026 – 06/11/2026" for several. */
export function leaveDays(leave: Pick<LeaveRequest, "from_on" | "to_on">): string {
  return leave.from_on === leave.to_on
    ? viDate(leave.from_on)
    : `${viDate(leave.from_on)} – ${viDate(leave.to_on)}`;
}
