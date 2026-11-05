import type { CellError, GradebookColumn } from "@/api/grades";

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

export const NOT_A_NUMBER = "Chưa phải số điểm.";

/** "2026-11-04T15:40:00Z" as "22:40 04/11/2026" in the browser's zone. */
export function stamp(iso: string): string {
  const at = new Date(iso);
  const time = at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  return `${time} ${at.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })}`;
}
