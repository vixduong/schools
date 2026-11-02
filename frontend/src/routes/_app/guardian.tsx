import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/guardian")({ component: Screen });

function Screen() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Con của bạn</h1>
      <p className="mt-2 italic text-ink-3">
        Điểm mới, chuyên cần, đơn xin nghỉ và thông báo của con sẽ hiện ở đây.
      </p>
    </section>
  );
}
