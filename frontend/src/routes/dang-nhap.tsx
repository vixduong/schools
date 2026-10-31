import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/dang-nhap")({ component: Login });

function Login() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Đăng nhập</h1>
      <p className="mt-2 italic text-ink-3">Biểu mẫu đăng nhập theo từng trường sẽ có ở đây.</p>
    </section>
  );
}
