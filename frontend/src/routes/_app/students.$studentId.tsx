import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/students/$studentId")({ component: Screen });

function Screen() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Hồ sơ học sinh</h1>
      <p className="mt-2 italic text-ink-3">
        Thông tin, điểm, chuyên cần và học bạ của học sinh sẽ hiện ở đây.
      </p>
    </section>
  );
}
