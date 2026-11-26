import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import { LEAVE_KEY, type LeaveRequest, leaveRequestsQuery } from "@/api/leave";
import {
  Field,
  FormError,
  fieldError,
  formMessage,
  invalidProps,
  useFocusRefused,
} from "@/components/auth-page";
import { Ticket } from "@/components/ticket";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LEAVE_STATES, leaveActionFailure, leaveDays } from "@/lib/leave";
import { FormFailure, refusal } from "@/lib/messages";

const GENERIC = "Không gửi được đơn. Kiểm tra lại các ngày rồi gửi lại.";

const FIELD: Record<string, Record<string, string>> = {
  from_on: {
    in_the_past: "Đơn chỉ xin nghỉ từ hôm nay trở đi. Với ngày đã qua, hãy báo cho giáo viên.",
    not_enrolled: "Con chưa học ở lớp nào vào ngày này.",
  },
  to_on: {
    before_from_on: "Ngày kết thúc không được trước ngày bắt đầu.",
    range_too_long: "Một đơn xin nghỉ tối đa 30 ngày.",
  },
};

/** The 400 of a send in Vietnamese: a day or the reason named under its field; a day already
 * covered by a waiting or approved request is the form's. */
function sendFailure(status: number, body: unknown) {
  if (status !== 400) return refusal(status, body, GENERIC);
  const error = (body ?? {}) as Record<string, string[] | undefined>;
  const fields: Record<string, string> = {};
  for (const [name, codes] of Object.entries(FIELD)) {
    const text = codes[error[name]?.[0] ?? ""];
    if (text) fields[name] = text;
  }
  if (error.reason?.length) fields.reason = "Cần ghi lý do xin nghỉ.";
  if (error.constraint?.includes("leaverequest_no_overlap"))
    return new FormFailure(
      "Con đã có đơn xin nghỉ đang chờ hoặc đã duyệt trong những ngày này.",
      {},
    );
  return new FormFailure(Object.keys(fields).length ? undefined : GENERIC, fields);
}

type Student = { id: number; name: string };

/** "Đơn xin nghỉ" on the Guardian view for the chosen child: the form, then the requests the
 * member sent for that child as tickets. */
export function LeaveBlock({ student }: { student: Student }) {
  const requests = useQuery(leaveRequestsQuery({ sent: 1 }));
  const sent = requests.data?.filter((leave) => leave.student === student.id);
  return (
    <section aria-labelledby="leave" className="mt-8 grid max-w-xl gap-6">
      <h2 id="leave" className="font-serif text-2xl font-light">
        Đơn xin nghỉ
      </h2>
      <LeaveForm key={student.id} student={student} />
      {requests.isError && (
        <p role="alert" className="text-destructive">
          Không tải được các đơn đã gửi. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {sent?.length === 0 && <p className="italic text-ink-3">Chưa có đơn nào.</p>}
      <ul aria-label="Các đơn đã gửi" className="grid gap-4">
        {sent?.map((leave) => (
          <li key={leave.id}>
            <SentTicket leave={leave} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function LeaveForm({ student }: { student: Student }) {
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const today = new Date().toLocaleDateString("sv"); // yyyy-mm-dd, local
  const [fromOn, setFromOn] = useState(today);
  const [toOn, setToOn] = useState(today);
  const [reason, setReason] = useState("");

  const send = useMutation({
    mutationFn: async () => {
      const { data, response, error } = await api.POST("/api/setup/leave-requests/", {
        body: { student: student.id, from_on: fromOn, to_on: toOn, reason: reason.trim() },
      });
      if (!data) throw sendFailure(response.status, error);
      return data;
    },
    onSuccess: () => {
      setReason("");
      queryClient.invalidateQueries({ queryKey: LEAVE_KEY });
    },
  });
  useFocusRefused(form, send.error);

  return (
    <form
      ref={form}
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        send.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="from_on" label="Từ ngày" error={fieldError(send.error, "from_on")}>
          <Input
            id="from_on"
            type="date"
            lang="vi"
            required
            min={today}
            value={fromOn}
            onChange={(event) => setFromOn(event.target.value)}
            {...invalidProps(send.error, "from_on")}
          />
        </Field>
        <Field id="to_on" label="Đến hết ngày" error={fieldError(send.error, "to_on")}>
          <Input
            id="to_on"
            type="date"
            lang="vi"
            required
            min={fromOn || today}
            value={toOn}
            onChange={(event) => setToOn(event.target.value)}
            {...invalidProps(send.error, "to_on")}
          />
        </Field>
      </div>
      <Field id="reason" label="Lý do" error={fieldError(send.error, "reason")}>
        <Input
          id="reason"
          required
          maxLength={500}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          {...invalidProps(send.error, "reason")}
        />
      </Field>
      <FormError message={formMessage(send.error)} />
      <div className="flex items-center gap-4">
        <Button type="submit" disabled={send.isPending}>
          Gửi đơn
        </Button>
        {send.isSuccess && (
          <p role="status" className="text-sm italic text-ink-3">
            Đã gửi đơn. Cô giáo chủ nhiệm sẽ xem.
          </p>
        )}
      </div>
    </form>
  );
}

function SentTicket({ leave }: { leave: LeaveRequest }) {
  const queryClient = useQueryClient();
  const state = LEAVE_STATES[leave.status];
  const cancel = useMutation({
    mutationFn: async () => {
      const { data, response, error } = await api.POST("/api/setup/leave-requests/{id}/cancel/", {
        params: { path: { id: leave.id } },
      });
      if (!data)
        throw leaveActionFailure(response.status, error, "Không huỷ được đơn: đơn đã được xử lý.");
      return data;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: LEAVE_KEY }),
  });
  return (
    <Ticket pin={state.pin} state={state.label} reference={leave.student_name}>
      <p className="tabular-nums">{leaveDays(leave)}</p>
      <p>{leave.reason}</p>
      {leave.status === "approved" && leave.decided_by_name && (
        <p className="text-sm text-ink-3">Duyệt bởi {leave.decided_by_name}</p>
      )}
      {leave.status === "approved" && leave.decision_comment && (
        <p className="text-sm">{leave.decision_comment}</p>
      )}
      {leave.status === "declined" && (
        <p className="text-sm text-destructive">
          {leave.decided_by_name ? `${leave.decided_by_name}: ` : ""}
          {leave.decision_comment}
        </p>
      )}
      {leave.status === "waiting" && (
        <div className="mt-2">
          <FormError message={formMessage(cancel.error)} />
          <Button variant="quiet" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            Huỷ đơn
          </Button>
        </div>
      )}
    </Ticket>
  );
}
