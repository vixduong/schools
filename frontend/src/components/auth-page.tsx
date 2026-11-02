import { useQuery } from "@tanstack/react-query";
import { type ReactNode, type RefObject, useEffect } from "react";
import { schoolQuery } from "@/api/queries";
import { FormFailure, NETWORK } from "@/lib/messages";

/** Login and activation: the host and the School's name lead, then one form (DESIGN.md, Login). */
export function AuthPage({ lead, children }: { lead: string; children: ReactNode }) {
  const school = useQuery(schoolQuery);
  return (
    <main className="container py-16">
      <div className="grid max-w-[420px] gap-4">
        <p className="text-sm text-secondary-foreground">{window.location.host}</p>
        <h1 className="font-serif text-4xl font-light [overflow-wrap:break-word]">
          {school.data?.name ?? (school.isError ? "Không tìm thấy trường" : " ")}
        </h1>
        <p className="italic text-ink-3">{lead}</p>
        {children}
        <p className="text-sm text-ink-3">
          Sai trường? Mỗi trường có địa chỉ riêng. Kiểm tra lại địa chỉ trên thanh trình duyệt.
        </p>
      </div>
    </main>
  );
}

/** A labelled field with its error under it (DESIGN.md, Controls). */
export function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="rounded-md bg-[var(--color-error-wash)] px-3 py-2 text-sm text-destructive"
    >
      {message}
    </p>
  );
}

/** The form-level message of a failed submit: the API's refusal, or a server problem. */
export function formMessage(error: Error | null): string | undefined {
  if (!error) return undefined;
  return error instanceof FormFailure ? error.form : NETWORK;
}

/** Props marking `name` invalid and pointing at its message, when the API refused it. */
export function invalidProps(error: Error | null, name: string) {
  return error instanceof FormFailure && error.fields[name]
    ? { "aria-invalid": true as const, "aria-describedby": `${name}-error` }
    : {};
}

/** After a refused submit, focus the first field the API refused (its message is read with it). */
export function useFocusRefused(form: RefObject<HTMLFormElement | null>, error: Error | null) {
  useEffect(() => {
    if (error) form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [error, form]);
}

export function fieldError(error: Error | null, name: string): string | undefined {
  return error instanceof FormFailure ? error.fields[name] : undefined;
}
