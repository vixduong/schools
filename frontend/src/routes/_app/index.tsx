import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/")({ component: Screen });

function Screen() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Hôm nay</h1>
      <p className="mt-2 italic text-ink-3">Việc của bạn hôm nay sẽ hiện ở đây.</p>
    </section>
  );
}
