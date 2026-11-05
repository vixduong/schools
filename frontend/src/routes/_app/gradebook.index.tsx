import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { api } from "@/api/client";
import { GRADEBOOK_KEY, type MyPair, myGradebooksQuery } from "@/api/grades";
import { FormError } from "@/components/auth-page";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_app/gradebook/")({ component: Screen });

const NO_SETUP: Record<string, string> = {
  no_subject_load:
    "Trường chưa nhập số tiết một năm của môn này ở khối này. Nhờ quản trị trường nhập ở Số tiết các môn.",
  no_profile_version: "Chưa có quy định đánh giá áp dụng cho lớp này. Hãy liên hệ nhà trường.",
};

function Screen() {
  const mine = useQuery(myGradebooksQuery);
  return (
    <section className="grid gap-6">
      <div>
        <h1 className="font-serif text-4xl font-light">Sổ điểm</h1>
        <p className="mt-2 italic text-ink-3">
          Chọn môn, lớp và học kỳ bạn dạy để vào sổ; chưa có sổ thì mở mới.
        </p>
      </div>
      {mine.isPending && <p className="italic text-ink-3">Đang tải các lớp bạn dạy…</p>}
      {mine.isError && (
        <p role="alert" className="text-destructive">
          Không tải được danh sách. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {mine.data?.length === 0 && (
        <p className="italic text-ink-3">Bạn chưa dạy môn nào ở lớp Trung học trong năm học này.</p>
      )}
      <ul className="grid max-w-2xl divide-y divide-border">
        {mine.data?.map((pair) => (
          <PairRow key={`${pair.subject}-${pair.school_class}`} pair={pair} />
        ))}
      </ul>
    </section>
  );
}

function PairRow({ pair }: { pair: MyPair }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [refused, setRefused] = useState<string>();
  const open = useMutation({
    mutationFn: async (term: number) => {
      const { data, response, error } = await api.POST("/api/setup/gradebooks/", {
        body: { term, subject: pair.subject, school_class: pair.school_class },
      });
      if (data) return data;
      const code = Object.values((error ?? {}) as Record<string, string[]>)
        .flat()
        .find((c) => c in NO_SETUP);
      throw new Error(
        code
          ? (NO_SETUP[code] as string)
          : response.status === 400
            ? "Không mở được sổ. Hãy liên hệ nhà trường."
            : "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại sau ít phút.",
      );
    },
    onSuccess: (book) => {
      queryClient.invalidateQueries({ queryKey: GRADEBOOK_KEY });
      navigate({ to: "/gradebook/$gradebookId", params: { gradebookId: String(book.id) } });
    },
    onError: (error) => setRefused(error.message),
  });
  return (
    <li className="grid gap-2 py-3">
      <p>
        <span className="font-semibold">{pair.subject_name}</span>
        <span className="text-ink-3"> · lớp {pair.class_name}</span>
      </p>
      <div className="flex flex-wrap gap-3">
        {pair.terms.map((term) =>
          term.gradebook ? (
            <Button key={term.term} asChild variant="secondary">
              <Link
                to="/gradebook/$gradebookId"
                params={{ gradebookId: String(term.gradebook) }}
                aria-label={`${term.term_name}, ${pair.subject_name} lớp ${pair.class_name}`}
              >
                {term.term_name}
              </Link>
            </Button>
          ) : (
            <Button
              key={term.term}
              variant="quiet"
              disabled={open.isPending}
              aria-label={`Mở sổ ${term.term_name}, ${pair.subject_name} lớp ${pair.class_name}`}
              onClick={() => {
                setRefused(undefined);
                open.mutate(term.term);
              }}
            >
              Mở sổ {term.term_name}
            </Button>
          ),
        )}
      </div>
      <FormError message={refused} />
    </li>
  );
}
