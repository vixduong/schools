import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "@/api/client";
import { type BellPeriod, bellPeriodsQuery } from "@/api/timetable";
import {
  Field,
  FormError,
  fieldError,
  formMessage,
  invalidProps,
  useFocusRefused,
} from "@/components/auth-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { FormFailure, refusal } from "@/lib/messages";
import { hhmm, inSchoolOrder, periodName, SESSIONS } from "@/lib/timetable";

const GENERIC = "Không lưu được giờ học. Kiểm tra giờ bắt đầu và giờ kết thúc rồi thử lại.";

/** The 400 of a bell period in Vietnamese: a clash of numbers or times out of order. */
function bellFailure(status: number, body: unknown) {
  const constraint = (body as { constraint?: string[] } | undefined)?.constraint?.[0];
  if (constraint === "bellperiod_ends_after_start")
    return new FormFailure(undefined, { ends_at: "Giờ kết thúc phải sau giờ bắt đầu." });
  if (constraint === "bellperiod_no_overlap")
    return new FormFailure(
      "Giờ học trùng với tiết khác: tiết sau bắt đầu khi tiết trước đã kết thúc.",
      {},
    );
  if (status === 400 && (body as { non_field_errors?: unknown } | undefined)?.non_field_errors)
    return new FormFailure("Tiết này đã có rồi.", {});
  return refusal(status, body, GENERIC);
}

type Fields = { starts_at: string; ends_at: string };

function TimesForm({
  id,
  period,
  schoolYear,
  canEdit,
}: {
  id: string;
  period?: BellPeriod;
  schoolYear: number;
  canEdit: boolean;
}) {
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const save = useMutation({
    mutationFn: async (body: Fields & { session: BellPeriod["session"]; number: number }) => {
      const { response, error } = period
        ? await api.PATCH("/api/setup/bell-periods/{id}/", {
            params: { path: { id: period.id } },
            body: { starts_at: body.starts_at, ends_at: body.ends_at },
          })
        : await api.POST("/api/setup/bell-periods/", {
            // `id` is read-only: the schema keeps it in the request type, the server ignores it.
            body: { school_year: schoolYear, ...body } as BellPeriod,
          });
      if (!response.ok) throw bellFailure(response.status, error);
    },
    onSuccess: () => {
      form.current?.reset();
      return queryClient.invalidateQueries({ queryKey: bellPeriodsQuery(schoolYear).queryKey });
    },
  });
  useFocusRefused(form, save.error);

  return (
    <form
      ref={form}
      aria-label={period ? periodName(period) : "Thêm tiết"}
      className="grid items-start gap-2 sm:grid-cols-[7rem_1fr_1fr_auto]"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        save.mutate({
          starts_at: String(data.get("starts_at")),
          ends_at: String(data.get("ends_at")),
          session: String(data.get("session")) === "afternoon" ? "afternoon" : "morning",
          number: Number(data.get("number") ?? 1),
        });
      }}
    >
      {period ? (
        <span className="self-center font-semibold">{periodName(period)}</span>
      ) : (
        <div className="flex gap-2">
          <NativeSelect name="session" aria-label="Buổi">
            {SESSIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect name="number" aria-label="Tiết số">
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
      <Field id={`${id}-starts_at`} label="Bắt đầu" error={fieldError(save.error, "starts_at")}>
        <Input
          id={`${id}-starts_at`}
          name="starts_at"
          type="time"
          required
          disabled={!canEdit}
          defaultValue={period ? hhmm(period.starts_at) : ""}
          {...invalidProps(save.error, "starts_at")}
        />
      </Field>
      <Field id={`${id}-ends_at`} label="Kết thúc" error={fieldError(save.error, "ends_at")}>
        <Input
          id={`${id}-ends_at`}
          name="ends_at"
          type="time"
          required
          disabled={!canEdit}
          defaultValue={period ? hhmm(period.ends_at) : ""}
          {...invalidProps(save.error, "ends_at")}
        />
      </Field>
      {canEdit && (
        <Button type="submit" variant="secondary" className="self-end" disabled={save.isPending}>
          {period ? "Lưu giờ" : "Thêm tiết"}
        </Button>
      )}
      <div className="sm:col-span-4">
        <FormError message={formMessage(save.error)} />
      </div>
    </form>
  );
}

/** The bell schedule of a school year, above the grid: one row per period, times editable. */
export function BellSchedule({
  periods,
  schoolYear,
  canEdit,
}: {
  periods: BellPeriod[];
  schoolYear: number;
  canEdit: boolean;
}) {
  return (
    <section aria-labelledby="bell-schedule" className="grid gap-3">
      <h2 id="bell-schedule" className="font-serif text-2xl font-light">
        Giờ học
      </h2>
      {periods.length === 0 && (
        <p className="italic text-ink-3">
          Chưa có tiết nào trong năm học này.
          {canEdit ? " Thêm các tiết dưới đây rồi xếp thời khóa biểu." : ""}
        </p>
      )}
      {inSchoolOrder(periods).map((period) => (
        <TimesForm
          key={`${period.id}-${period.starts_at}-${period.ends_at}`}
          id={`bell-${period.id}`}
          period={period}
          schoolYear={schoolYear}
          canEdit={canEdit}
        />
      ))}
      {canEdit && <TimesForm id="bell-new" schoolYear={schoolYear} canEdit />}
    </section>
  );
}
