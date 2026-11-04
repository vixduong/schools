import type { LeaveRequest } from "@/api/leave";
import type { Pin } from "@/components/ticket";
import { viDate } from "@/lib/attendance";
import { FormFailure, refusal } from "@/lib/messages";

const NO_RIGHT = "Bạn không còn quyền với đơn này. Tải lại trang để xem.";
const OWN_REQUEST = "Đơn do chính bạn gửi nên bạn không tự duyệt được. Nhờ người khác duyệt.";

/** A refused approve, decline or cancel in Vietnamese: a 403 (the student moved class, the link
 * ended) and a request of one's own have words; the rest is `refusal`. */
export function leaveActionFailure(status: number, body: unknown, generic: string): Error {
  if (status === 403) return new FormFailure(NO_RIGHT, {});
  if (
    status === 400 &&
    (body as { status?: string[] } | undefined)?.status?.includes("own_request")
  )
    return new FormFailure(OWN_REQUEST, {});
  return refusal(status, body, generic);
}

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
