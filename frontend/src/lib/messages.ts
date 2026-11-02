import type { FieldErrors } from "@/api/client";

// The API answers in codes and English; people read Vietnamese (docs/slices/slice-8.md).
export const NETWORK = "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.";
export const INVALID_LOGIN = "Sai số điện thoại, email hoặc mật khẩu.";
export const INVALID_INVITATION = "Mã mời không đúng hoặc đã hết hạn.";
export const CANNOT_APPLY = "Không dùng được mã mời này. Hãy liên hệ nhà trường.";

const FIELD: Record<string, string> = {
  password: "Mật khẩu quá ngắn hoặc quá dễ đoán. Chọn mật khẩu khác, ít nhất 8 ký tự.",
  identifier: "Số điện thoại hoặc email không hợp lệ.",
  code: "Nhập mã mời.",
};

/** A refused form: one message for the form, one per field. */
export class FormFailure extends Error {
  constructor(
    readonly form: string | undefined,
    readonly fields: Record<string, string>,
  ) {
    super(form ?? "form");
  }
}

/** The refusal in a 400 body, in Vietnamese. */
export function readErrors(body: FieldErrors | undefined, generic: string): FormFailure {
  const fields: Record<string, string> = {};
  let form: string | undefined;
  for (const [name, messages] of Object.entries(body ?? {})) {
    if (!messages?.length) continue;
    const message = FIELD[name];
    if (message) fields[name] = message;
    else if (name === "invitation" || name === "constraint") form = CANNOT_APPLY;
    else form = generic;
  }
  return new FormFailure(form ?? (Object.keys(fields).length ? undefined : generic), fields);
}

/** `redirect` from the URL, only a path on this site (never `//other.host`). */
export function safeRedirect(value: unknown): string | undefined {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//")
    ? value
    : undefined;
}
