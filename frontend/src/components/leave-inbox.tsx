import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import { LEAVE_KEY, type LeaveRequest, leaveRequestsQuery } from "@/api/leave";
import { FormError, formMessage } from "@/components/auth-page";
import { Ticket } from "@/components/ticket";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { leaveActionFailure, leaveDays } from "@/lib/leave";

const GENERIC = "Không xử lý được đơn. Đơn có thể đã được xử lý: tải lại trang để xem.";

/** The leave part of "Cần cô xử lý" on the teacher home: one pinned ticket per waiting leave
 * request, with Duyệt and Từ chối; Từ chối asks for the reason first. */
export function LeaveTickets() {
  const waiting = useQuery(leaveRequestsQuery({ status: "waiting", to_decide: 1 }));
  return (
    <>
      {waiting.isPending && <p className="italic text-ink-3">Đang tải các đơn xin nghỉ…</p>}
      {waiting.isError && (
        <p role="alert" className="text-destructive">
          Không tải được các đơn xin nghỉ. Kiểm tra mạng rồi tải lại trang.
        </p>
      )}
      {waiting.data?.length === 0 && (
        <p className="italic text-ink-3">Không có đơn xin nghỉ nào đang chờ cô.</p>
      )}
      {waiting.data?.map((leave) => (
        <InboxTicket key={leave.id} leave={leave} />
      ))}
    </>
  );
}

function InboxTicket({ leave }: { leave: LeaveRequest }) {
  const queryClient = useQueryClient();
  const [declining, setDeclining] = useState(false);
  const [comment, setComment] = useState("");
  const [missing, setMissing] = useState(false);
  const field = useRef<HTMLInputElement>(null);

  const decide = useMutation({
    mutationFn: async (action: "approve" | "decline") => {
      const params = { path: { id: leave.id } };
      const { data, response, error } =
        action === "approve"
          ? await api.POST("/api/setup/leave-requests/{id}/approve/", {
              params,
              body: { comment: "" },
            })
          : await api.POST("/api/setup/leave-requests/{id}/decline/", {
              params,
              body: { comment: comment.trim() },
            });
      if (!data) throw leaveActionFailure(response.status, error, GENERIC);
      return data;
    },
    // Decided or not, the list is the server's word.
    onSettled: () => queryClient.invalidateQueries({ queryKey: LEAVE_KEY }),
  });

  function submitDecline() {
    if (!comment.trim()) {
      setMissing(true);
      field.current?.focus();
      return;
    }
    decide.mutate("decline");
  }

  const commentId = `decline-${leave.id}`;
  return (
    <Ticket
      pin="alert"
      state="Đơn xin nghỉ"
      reference={`${leave.student_name}${leave.class_name ? ` · lớp ${leave.class_name}` : ""}`}
    >
      <p className="tabular-nums">{leaveDays(leave)}</p>
      <p>{leave.reason}</p>
      <p className="text-sm text-ink-3">Gửi bởi {leave.sent_by_name}</p>
      <FormError message={formMessage(decide.error)} />
      {declining ? (
        <div className="mt-2 grid gap-2">
          <Input
            id={commentId}
            ref={field}
            aria-label={`Lý do từ chối, ${leave.student_name}`}
            placeholder="Lý do từ chối"
            maxLength={500}
            value={comment}
            onChange={(event) => {
              setComment(event.target.value);
              setMissing(false);
            }}
            {...(missing ? { "aria-invalid": true, "aria-describedby": `${commentId}-error` } : {})}
          />
          {missing && (
            <p id={`${commentId}-error`} className="text-sm text-destructive">
              Cần ghi lý do từ chối để phụ huynh biết.
            </p>
          )}
          <div className="flex gap-2">
            <Button variant="destructive" disabled={decide.isPending} onClick={submitDecline}>
              Gửi từ chối
            </Button>
            <Button variant="quiet" onClick={() => setDeclining(false)}>
              Thôi
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex gap-2">
          <Button
            variant="secondary"
            disabled={decide.isPending}
            onClick={() => decide.mutate("approve")}
          >
            Duyệt
          </Button>
          <Button
            variant="destructive"
            disabled={decide.isPending}
            onClick={() => setDeclining(true)}
          >
            Từ chối
          </Button>
        </div>
      )}
    </Ticket>
  );
}
