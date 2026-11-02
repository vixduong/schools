import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useRef } from "react";
import { api } from "@/api/client";
import { meQuery } from "@/api/queries";
import {
  AuthPage,
  Field,
  FormError,
  fieldError,
  formMessage,
  invalidProps,
  useFocusRefused,
} from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { INVALID_INVITATION, refusal, safeRedirect } from "@/lib/messages";

export const Route = createFileRoute("/activate")({
  validateSearch: (search): { redirect?: string } => {
    const redirect = safeRedirect(search.redirect);
    return redirect ? { redirect } : {};
  },
  component: Activate,
});

type Body = { code: string; identifier: string; password: string; display_name?: string };

function Activate() {
  const { redirect } = Route.useSearch();
  const router = useRouter();
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const activate = useMutation({
    mutationFn: async (body: Body) => {
      const { data, error, response } = await api.POST("/api/auth/activate/", { body });
      if (!data) throw refusal(response.status, error, INVALID_INVITATION);
      return data;
    },
    onSuccess: (me) => {
      queryClient.clear(); // nothing of a previous person stays cached
      queryClient.setQueryData(meQuery.queryKey, me);
      router.history.push(redirect ?? "/");
    },
  });
  useFocusRefused(form, activate.error);
  const error = activate.error;

  return (
    <AuthPage lead="Kích hoạt tài khoản bằng mã mời nhà trường đã gửi hoặc in cho bạn.">
      <form
        ref={form}
        className="grid gap-4 border-t border-border pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          const name = String(data.get("display_name")).trim();
          activate.mutate({
            code: String(data.get("code")),
            identifier: String(data.get("identifier")),
            password: String(data.get("password")),
            ...(name ? { display_name: name } : {}),
          });
        }}
      >
        <FormError message={formMessage(error)} />
        <Field id="code" label="Mã mời" error={fieldError(error, "code")}>
          <Input
            id="code"
            name="code"
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="XXXXX-XXXXX"
            required
            {...invalidProps(error, "code")}
          />
        </Field>
        <Field
          id="identifier"
          label="Số điện thoại hoặc email"
          error={fieldError(error, "identifier")}
        >
          <Input
            id="identifier"
            name="identifier"
            autoComplete="username"
            required
            {...invalidProps(error, "identifier")}
          />
        </Field>
        <Field id="password" label="Mật khẩu" error={fieldError(error, "password")}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            {...invalidProps(error, "password")}
            aria-describedby={[fieldError(error, "password") && "password-error", "password-hint"]
              .filter(Boolean)
              .join(" ")}
          />
          <p id="password-hint" className="text-sm italic text-ink-3">
            Đã có tài khoản ở trường khác? Nhập đúng mật khẩu đó để dùng chung.
          </p>
        </Field>
        <Field
          id="display_name"
          label="Họ và tên (không bắt buộc)"
          error={fieldError(error, "display_name")}
        >
          <Input
            id="display_name"
            name="display_name"
            autoComplete="name"
            {...invalidProps(error, "display_name")}
          />
        </Field>
        <Button type="submit" className="w-full" disabled={activate.isPending}>
          {activate.isPending ? "Đang kích hoạt…" : "Kích hoạt và đăng nhập"}
        </Button>
        <Link to="/login" search={{ redirect }} className="text-sm underline underline-offset-4">
          Đã kích hoạt rồi? Đăng nhập
        </Link>
      </form>
    </AuthPage>
  );
}
