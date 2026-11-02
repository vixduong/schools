import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { api, type FieldErrors } from "@/api/client";
import { meQuery } from "@/api/queries";
import { AuthPage, Field, FormError } from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormFailure, INVALID_INVITATION, NETWORK, readErrors } from "@/lib/messages";

export const Route = createFileRoute("/activate")({ component: Activate });

type Body = { code: string; identifier: string; password: string; display_name?: string };

function Activate() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const activate = useMutation({
    mutationFn: async (body: Body) => {
      const { data, error } = await api.POST("/api/auth/activate/", { body });
      if (error || !data) throw readErrors(error as FieldErrors, INVALID_INVITATION);
      return data;
    },
    onSuccess: (me) => {
      queryClient.setQueryData(meQuery.queryKey, me);
      router.history.push("/");
    },
  });
  const failure = activate.error instanceof FormFailure ? activate.error : undefined;
  const invalid = (name: string) =>
    failure?.fields[name] ? { "aria-invalid": true, "aria-describedby": `${name}-error` } : {};

  return (
    <AuthPage lead="Kích hoạt tài khoản bằng mã mời nhà trường đã gửi hoặc in cho bạn.">
      <form
        className="grid gap-4 border-t border-border pt-4"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const name = String(form.get("display_name")).trim();
          activate.mutate({
            code: String(form.get("code")),
            identifier: String(form.get("identifier")),
            password: String(form.get("password")),
            ...(name ? { display_name: name } : {}),
          });
        }}
      >
        <FormError message={failure?.form ?? (activate.error && !failure ? NETWORK : undefined)} />
        <Field id="code" label="Mã mời" error={failure?.fields.code}>
          <Input
            id="code"
            name="code"
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="XXXXX-XXXXX"
            required
            {...invalid("code")}
          />
        </Field>
        <Field id="identifier" label="Số điện thoại hoặc email" error={failure?.fields.identifier}>
          <Input
            id="identifier"
            name="identifier"
            autoComplete="username"
            required
            {...invalid("identifier")}
          />
        </Field>
        <Field id="password" label="Mật khẩu" error={failure?.fields.password}>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            {...invalid("password")}
          />
          <p className="text-sm italic text-ink-3">
            Đã có tài khoản ở trường khác? Nhập đúng mật khẩu đó để dùng chung.
          </p>
        </Field>
        <Field id="display_name" label="Họ và tên (không bắt buộc)">
          <Input id="display_name" name="display_name" autoComplete="name" />
        </Field>
        <Button type="submit" className="w-full" disabled={activate.isPending}>
          {activate.isPending ? "Đang kích hoạt…" : "Kích hoạt và đăng nhập"}
        </Button>
        <Link to="/login" className="text-sm underline underline-offset-4">
          Đã kích hoạt rồi? Đăng nhập
        </Link>
      </form>
    </AuthPage>
  );
}
