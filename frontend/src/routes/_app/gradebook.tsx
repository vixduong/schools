import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/gradebook")({ component: Screen });

function Screen() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Sổ điểm</h1>
      <p className="mt-2 italic text-ink-3">
        Sổ điểm các lớp cô dạy sẽ hiện ở đây, theo môn và học kỳ.
      </p>
    </section>
  );
}
