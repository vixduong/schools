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
const DRF_DENIED = "You do not have permission to perform this action.";
const NO_RIGHT = "Bạn không còn quyền với bước này. Tải lại trang để xem.";
const NEEDS_TEXT = "Cần ghi lý do.";
const TOO_LONG = "Lý do tối đa 500 ký tự.";
const RULE = "Sổ điểm không đổi được vì một quy định của hệ thống. Hãy liên hệ nhà trường.";

/** A refused step in Vietnamese; a missing comment or reason comes back as a field of the body. */
export function stepFailure(status: number, body: unknown, generic: string): Error {
  // The role refusal is DRF's own 403; any other (a failed CSRF check) is not about the role.
  if (status === 403) {
    const detail = (body as { detail?: string } | undefined)?.detail;
    return new FormFailure(detail === DRF_DENIED ? NO_RIGHT : generic, {});
  }
  if (status !== 400) return refusal(status, body, generic);
  const refused = body as
    | { status?: string[]; comment?: string[]; reason?: string[]; constraint?: string[] }
    | undefined;
  if (refused?.status?.includes("own_submission")) return new FormFailure(OWN_SUBMISSION, {});
  if (refused?.status?.length) return new FormFailure(STALE, {});
  const text = [...(refused?.comment ?? []), ...(refused?.reason ?? [])];
  if (text.length)
    return new FormFailure(undefined, { text: text.includes("too_long") ? TOO_LONG : NEEDS_TEXT });
  // A student enrolled meanwhile: the book changed under the reviewer, as for a status change.
  if (refused?.constraint?.includes("gradebook_incomplete")) return new FormFailure(STALE, {});
  if (refused?.constraint?.length) return new FormFailure(RULE, {});
  return new FormFailure(generic, {});
}

export const MAX_DOCUMENT_MB = 10;

const CARRIED_FIELD: Record<string, string> = {
  required: "Cần điền.",
  too_long: "Quá dài.",
  too_large: `Tệp quá lớn (tối đa ${MAX_DOCUMENT_MB} MB).`,
  unsupported_type: "Chỉ nhận PDF, JPEG hoặc PNG.",
};
const CARRIED_RESULT: Record<string, string> = {
  out_of_range: "Điểm từ 0 đến 10.",
  too_many_decimals: "Điểm chỉ có một chữ số thập phân.",
  wrong_form: "Ô này không nhận kiểu điểm đó.",
  unknown_column: "Sổ không có cột này.",
};

/** The refusal of the transfer record or of the carried results, in Vietnamese: a message per
 * field (`source_school`, `document`) or per result (`kind:index`, as the dialog keys them). */
export function carriedFailure(status: number, body: unknown): Error {
  const generic = "Không lưu được. Tải lại trang rồi thử lại; những gì bạn nhập chưa mất.";
  if (status === 403)
    return new FormFailure("Bạn không có quyền nhập kết quả mang sang cho học sinh này.", {});
  if (status !== 400) return refusal(status, body, generic);
  const refused = body as
    | {
        student?: string[];
        gradebook?: string[];
        constraint?: string[];
        source_school?: string[];
        document?: string[];
        results?: ({ kind: string; index: number; code: string } | string)[];
      }
    | undefined;
  if (refused?.student?.length)
    return new FormFailure("Học sinh này không phải học sinh chuyển đến trong học kỳ này.", {});
  if (refused?.gradebook?.length) return new FormFailure("Sổ đã nộp, không sửa được.", {});
  const fields: Record<string, string> = {};
  for (const name of ["source_school", "document"] as const) {
    const code = refused?.[name]?.[0];
    if (code) fields[name] = CARRIED_FIELD[code] ?? generic;
  }
  for (const item of refused?.results ?? [])
    if (typeof item !== "string")
      fields[`${item.kind}:${item.index}`] = CARRIED_RESULT[item.code] ?? generic;
  if (Object.keys(fields).length) return new FormFailure(undefined, fields);
  return new FormFailure(refused?.constraint?.length ? RULE : generic, {});
}
