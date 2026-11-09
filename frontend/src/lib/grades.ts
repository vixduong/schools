import type { CellError, GradebookColumn, GradebookDetail, StepAction } from "@/api/grades";
import { FormFailure, refusal } from "@/lib/messages";

/** TX1…TXn for the regular columns, GK for mid-term, CK for end-term. */
export function columnLabel(column: Pick<GradebookColumn, "kind" | "index">): string {
  if (column.kind === "regular") return `TX${column.index}`;
  return column.kind === "mid_term" ? "GK" : "CK";
}

/** A score as people write it in Vietnamese: 7,5. */
export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value).replace(".", ",");
}

export type Parsed = { kind: "clear" } | { kind: "value"; value: number } | { kind: "invalid" };

/** What the text typed in a score cell means. Never `NaN`: JSON would send it as null, which
 * clears the cell. */
export function parseScore(text: string): Parsed {
  const trimmed = text.trim().replace(",", ".");
  if (trimmed === "") return { kind: "clear" };
  return /^\d{1,3}(\.\d*)?$/.test(trimmed)
    ? { kind: "value", value: Number(trimmed) }
    : { kind: "invalid" };
}

export const RESULTS = [
  { value: "pass", label: "Đạt" },
  { value: "fail", label: "Chưa đạt" },
] as const;

export function resultLabel(result: string | null | undefined): string {
  return RESULTS.find((r) => r.value === result)?.label ?? "";
}

export const CELL_ERROR: Record<CellError["code"], string> = {
  conflict: "Người khác vừa lưu ô này.",
  out_of_range: "Điểm từ 0 đến 10.",
  too_many_decimals: "Điểm chỉ có một chữ số thập phân.",
  wrong_form: "Ô này không nhận kiểu điểm đó.",
  not_enrolled: "Học sinh không còn trong lớp.",
};

export const INCOMPLETE = "Chưa có điểm";

export const NOT_A_NUMBER = "Chưa phải số điểm.";

/** "2026-11-04T15:40:00Z" as "22:40 04/11/2026" in the browser's zone. */
export function stamp(iso: string): string {
  const at = new Date(iso);
  const time = at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  return `${time} ${at.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}`;
}

/** The three states of a gradebook, in lifecycle order (DESIGN.md, Gradebook grid). */
export const LIFECYCLE: { status: GradebookDetail["status"]; label: string }[] = [
  { status: "draft", label: "Đang nhập" },
  { status: "submitted", label: "Chờ duyệt" },
  { status: "approved", label: "Đã khoá" },
];

/** A step as the list under the grid words it. */
export const STEP_LABEL: Record<StepAction, string> = {
  submit: "Đã nộp",
  withdraw: "Đã rút lại",
  return: "Trả lại",
  approve: "Đã duyệt",
  reopen: "Mở lại",
};

const STALE = "Sổ điểm vừa đổi trạng thái. Tải lại trang để xem.";
const OWN_SUBMISSION = "Bạn đã nộp sổ này nên không tự duyệt hoặc trả lại được. Nhờ người khác.";
const NO_RIGHT = "Bạn không còn quyền với bước này. Tải lại trang để xem.";
const NEEDS_TEXT = "Cần ghi lý do.";
const RULE = "Sổ điểm không đổi được vì một quy định của hệ thống. Hãy liên hệ nhà trường.";

/** A refused step in Vietnamese; a missing comment or reason comes back as a field of the body. */
export function stepFailure(status: number, body: unknown, generic: string): Error {
  if (status === 403) return new FormFailure(NO_RIGHT, {});
  if (status !== 400) return refusal(status, body, generic);
  const refused = body as
    | { status?: string[]; comment?: string[]; reason?: string[]; constraint?: string[] }
    | undefined;
  if (refused?.status?.includes("own_submission")) return new FormFailure(OWN_SUBMISSION, {});
  if (refused?.status?.length) return new FormFailure(STALE, {});
  if (refused?.comment?.length || refused?.reason?.length)
    return new FormFailure(undefined, { text: NEEDS_TEXT });
  if (refused?.constraint?.length) return new FormFailure(RULE, {});
  return new FormFailure(generic, {});
}
