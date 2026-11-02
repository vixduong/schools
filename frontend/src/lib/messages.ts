import type { FieldErrors } from "@/api/client";

// The API answers in codes and English; people read Vietnamese (docs/slices/slice-8.md).
export const NETWORK = "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại sau ít phút.";
export const INVALID_LOGIN = "Sai số điện thoại, email hoặc mật khẩu.";
export const INVALID_INVITATION = "Mã mời không đúng hoặc đã hết hạn.";
export const TOO_MANY = "Bạn đã thử quá nhiều lần. Đợi 15 phút rồi thử lại.";
export const CANNOT_APPLY = "Không dùng được mã mời này. Hãy liên hệ nhà trường.";

const FIELD: Record<string, string> = {
  password: "Mật khẩu quá ngắn hoặc quá dễ đoán. Chọn mật khẩu khác, ít nhất 8 ký tự.",
  identifier: "Số điện thoại hoặc email không hợp lệ.",
  code: "Mã mời không hợp lệ. Mã có dạng XXXXX-XXXXX.",
  display_name: "Họ và tên quá dài.",
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

/** The refusal of a form submit: the API's 400 in Vietnamese; anything else (a 5xx, a CSRF 403,
 * a proxy's HTML page) is no verdict on what the person typed, so it reads as a server problem. */
export function refusal(status: number, body: unknown, generic: string): Error {
  if (status === 400) return readErrors(body as FieldErrors, generic);
  if (status === 429) return new FormFailure(TOO_MANY, {});
  return new Error(`HTTP ${status}`);
}

/** `redirect` from the URL, only a path on this site (never `//other.host` or `/\other.host`). */
export function safeRedirect(value: unknown): string | undefined {
  if (typeof value !== "string" || !value.startsWith("/")) return undefined;
  try {
    return new URL(value, window.location.origin).origin === window.location.origin
      ? value
      : undefined;
  } catch {
    return undefined;
  }
}
