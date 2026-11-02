import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { api, type FieldErrors } from "@/api/client";
import { meQuery } from "@/api/queries";
import { AuthPage, Field, FormError } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormFailure, INVALID_LOGIN, NETWORK, readErrors, safeRedirect } from "@/lib/messages";

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
  const login = useMutation({
    mutationFn: async (body: { identifier: string; password: string }) => {
      const { data, error } = await api.POST("/api/auth/login/", { body });
      if (error || !data) throw readErrors(error as FieldErrors, INVALID_LOGIN);
      return data;
    },
    onSuccess: (me) => {
      queryClient.setQueryData(meQuery.queryKey, me);
      router.history.push(redirect ?? "/");
    },
  });
  const failure = login.error instanceof FormFailure ? login.error : undefined;

  return (
    <AuthPage lead="Đăng nhập để vào sổ điểm, điểm danh và thông báo của trường.">
      <form
        className="grid gap-4 border-t border-border pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          login.mutate({
            identifier: String(form.get("identifier")),
            password: String(form.get("password")),
          });
        }}
      >
        <FormError message={failure?.form ?? (login.error && !failure ? NETWORK : undefined)} />
        <Field id="identifier" label="Số điện thoại hoặc email">
          <Input id="identifier" name="identifier" autoComplete="username" required />
        </Field>
        <Field id="password" label="Mật khẩu">
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </Field>
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Đang đăng nhập…" : "Đăng nhập"}
        </Button>
        <div className="flex flex-wrap justify-between gap-2 text-sm">
          <Link to="/activate" className="underline underline-offset-4">
            Phụ huynh, học sinh: kích hoạt bằng mã mời
          </Link>
          <span className="text-ink-3">Quên mật khẩu? Hỏi quản trị trường của bạn.</span>
        </div>
      </form>
    </AuthPage>
  );
}
