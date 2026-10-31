import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({ component: TeacherHome });

function TeacherHome() {
  return (
    <section>
      <h1 className="font-serif text-4xl font-light">Hôm nay</h1>
      <p className="mt-2 italic text-ink-3">Các tiết dạy và hồ sơ của cô sẽ hiện ở đây.</p>
    </section>
  );
}
