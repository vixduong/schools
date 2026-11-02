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
import { INVALID_LOGIN, refusal, safeRedirect } from "@/lib/messages";

export const Route = createFileRoute("/login")({
  validateSearch: (search): { redirect?: string } => {
    const redirect = safeRedirect(search.redirect);
    return redirect ? { redirect } : {};
  },
  component: Login,
});

function Login() {
  const { redirect } = Route.useSearch();
  const router = useRouter();
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const login = useMutation({
    mutationFn: async (body: { identifier: string; password: string }) => {
      const { data, error, response } = await api.POST("/api/auth/login/", { body });
      if (!data) throw refusal(response.status, error, INVALID_LOGIN);
      return data;
    },
    onSuccess: (me) => {
      queryClient.clear(); // nothing of a previous person stays cached
      queryClient.setQueryData(meQuery.queryKey, me);
      router.history.push(redirect ?? "/");
    },
  });
  useFocusRefused(form, login.error);

  return (
    <AuthPage lead="Đăng nhập để vào sổ điểm, điểm danh và thông báo của trường.">
      <form
        ref={form}
        className="grid gap-4 border-t border-border pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          login.mutate({
            identifier: String(data.get("identifier")),
            password: String(data.get("password")),
          });
        }}
      >
        <FormError message={formMessage(login.error)} />
        <Field
          id="identifier"
          label="Số điện thoại hoặc email"
          error={fieldError(login.error, "identifier")}
        >
          <Input
            id="identifier"
            name="identifier"
            autoComplete="username"
            required
            {...invalidProps(login.error, "identifier")}
          />
        </Field>
        <Field id="password" label="Mật khẩu" error={fieldError(login.error, "password")}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            {...invalidProps(login.error, "password")}
          />
        </Field>
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Đang đăng nhập…" : "Đăng nhập"}
        </Button>
        <div className="flex flex-wrap justify-between gap-2 text-sm">
          <Link to="/activate" search={{ redirect }} className="underline underline-offset-4">
            Phụ huynh, học sinh: kích hoạt bằng mã mời
          </Link>
          <span className="text-ink-3">Quên mật khẩu? Hỏi quản trị trường của bạn.</span>
        </div>
      </form>
    </AuthPage>
  );
}
