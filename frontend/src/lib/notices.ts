import type { Audience } from "@/api/notices";
import { FormFailure, refusal } from "@/lib/messages";

export const MAX_TITLE = 200;
export const MAX_BODY = 5000;

const GENERIC = "Không gửi được thông báo. Kiểm tra lại rồi gửi lại.";
const NO_RIGHT = "Bạn không còn quyền gửi thông báo đến nhóm này. Tải lại trang để xem.";
const NO_AUDIENCE = "Nhóm người nhận này không còn nữa. Chọn nhóm khác.";

// The API's error codes per field, in Vietnamese.
const FIELD: Record<string, Record<string, string>> = {
  audience: { unknown: NO_AUDIENCE },
  school_class: { unknown: NO_AUDIENCE },
  subject_group: { unknown: NO_AUDIENCE },
  title: {
    required: "Cần nhập tiêu đề.",
    too_long: `Tiêu đề tối đa ${MAX_TITLE} ký tự.`,
    single_line: "Tiêu đề chỉ viết trên một dòng.",
  },
  body: {
    required: "Cần nhập nội dung.",
    too_long: `Nội dung tối đa ${MAX_BODY} ký tự.`,
  },
};

/** The refusal of a send in Vietnamese: a code per field under that field (a refused class or
 * group is the audience's), an empty audience or a constraint for the form. */
export function sendFailure(status: number, body: unknown): Error {
  if (status === 403) return new FormFailure(NO_RIGHT, {});
  if (status !== 400) return refusal(status, body, GENERIC);
  const error = (body ?? {}) as Record<string, string[] | undefined>;
  const fields: Record<string, string> = {};
  for (const [name, codes] of Object.entries(FIELD)) {
    const text = codes[error[name]?.[0] ?? ""];
    if (!text) continue;
    const field = name === "school_class" || name === "subject_group" ? "audience" : name;
    fields[field] ??= text;
  }
  if (error.recipients?.includes("none"))
    return new FormFailure("Nhóm người nhận này hiện chưa có ai nhận được thông báo.", {});
  return new FormFailure(Object.keys(fields).length ? undefined : GENERIC, fields);
}

/** The choice's label: "Toàn trường", "Tổ Toán", "Phụ huynh lớp 7A", "Phụ huynh và học sinh lớp 7B". */
export function audienceLabel(
  entry: Pick<Audience, "audience" | "school_class" | "subject_group">,
) {
  switch (entry.audience) {
    case "school":
      return "Toàn trường";
    case "group":
      return `Tổ ${entry.subject_group?.name ?? ""}`;
    case "homeroom_guardians":
      return `Phụ huynh lớp ${entry.school_class?.name ?? ""}`;
    case "class":
      return `Phụ huynh và học sinh lớp ${entry.school_class?.name ?? ""}`;
  }
}

/** One option value per entry: the audience and its target. */
export const audienceValue = (entry: Audience) =>
  `${entry.audience}:${entry.school_class?.id ?? entry.subject_group?.id ?? ""}`;
