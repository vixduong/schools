import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import {
  type Audience,
  NOTICES_KEY,
  noticeAudiencesQuery,
  type ReceivedNotice,
  receivedNoticesQuery,
  type SentNotice,
  sentNoticesQuery,
} from "@/api/notices";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  audienceLabel,
  audienceValue,
  MAX_BODY,
  MAX_TITLE,
  sendFailure,
  sentDay,
} from "@/lib/notices";
import { cn } from "@/lib/utils";

const LOAD_FAILED = "Không tải được thông báo. Kiểm tra mạng rồi tải lại trang.";

/** "Thông báo": what the member received; a member who may send also gets Đã gửi and the composer. */
export function NoticesScreen() {
  const audiences = useQuery(noticeAudiencesQuery);
  const canSend = !!audiences.data?.length;
  const [composing, setComposing] = useState(false);
  return (
    <section aria-labelledby="notices" className="grid max-w-xl gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 id="notices" className="font-serif text-4xl font-light">
          Thông báo
        </h1>
        {canSend && <Button onClick={() => setComposing(true)}>Gửi thông báo</Button>}
      </div>
      <Tabs defaultValue="received">
        <TabsList variant="line">
          <TabsTrigger value="received">Đã nhận</TabsTrigger>
          {canSend && <TabsTrigger value="sent">Đã gửi</TabsTrigger>}
        </TabsList>
        <TabsContent value="received" className="pt-4">
          <ReceivedList />
        </TabsContent>
        {canSend && (
          <TabsContent value="sent" className="pt-4">
            <SentList />
          </TabsContent>
        )}
      </Tabs>
      {composing && audiences.data && (
        <Composer audiences={audiences.data} onClose={() => setComposing(false)} />
      )}
    </section>
  );
}

function ReceivedList() {
  const notices = useQuery(receivedNoticesQuery);
  return (
    <div className="grid gap-4">
      {notices.isPending && <p className="italic text-ink-3">Đang tải…</p>}
      {notices.isError && (
        <p role="alert" className="text-destructive">
          {LOAD_FAILED}
        </p>
      )}
      {notices.data?.length === 0 && <p className="italic text-ink-3">Chưa có thông báo nào.</p>}
      {notices.data?.map((notice) => (
        <ReceivedCard key={notice.id} notice={notice} />
      ))}
    </div>
  );
}

function ReceivedCard({ notice }: { notice: ReceivedNotice }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const unread = notice.read_at === null;
  const read = useMutation({
    mutationFn: async () => {
      const { data } = await api.POST("/api/setup/notices/{id}/read/", {
        params: { path: { id: notice.id } },
      });
      return data;
    },
    // Marked or not, the list is the server's word.
    onSettled: () => queryClient.invalidateQueries({ queryKey: NOTICES_KEY }),
  });
  return (
    <Ticket
      pin={unread ? "open" : "locked"}
      state={notice.title}
      reference={`${notice.sender_name} · ${sentDay(notice.sent_at)}`}
    >
      {unread && (
        <span
          role="img"
          aria-label="Chưa đọc"
          className="absolute top-3 right-4 size-2.5 rounded-full bg-primary"
        />
      )}
      {open && <p className="whitespace-pre-wrap">{notice.body}</p>}
      <div className="mt-2">
        <Button
          variant="quiet"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open);
            if (!open && unread && !read.isPending) read.mutate();
          }}
        >
          {open ? "Thu gọn" : "Đọc"}
        </Button>
      </div>
    </Ticket>
  );
}

function SentList() {
  const notices = useQuery(sentNoticesQuery);
  return (
    <div className="grid gap-4">
      {notices.isPending && <p className="italic text-ink-3">Đang tải…</p>}
      {notices.isError && (
        <p role="alert" className="text-destructive">
          {LOAD_FAILED}
        </p>
      )}
      {notices.data?.length === 0 && (
        <p className="italic text-ink-3">Bạn chưa gửi thông báo nào.</p>
      )}
      {notices.data?.map((notice) => (
        <SentCard key={notice.id} notice={notice} />
      ))}
    </div>
  );
}

function SentCard({ notice }: { notice: SentNotice }) {
  const target = audienceLabel({
    audience: notice.audience,
    school_class: notice.school_class_name ? { id: 0, name: notice.school_class_name } : undefined,
    subject_group: notice.subject_group_name
      ? { id: 0, name: notice.subject_group_name }
      : undefined,
  });
  return (
    <Ticket pin="locked" state={notice.title} reference={`${target} · ${sentDay(notice.sent_at)}`}>
      <p className="whitespace-pre-wrap">{notice.body}</p>
      <p className="text-sm tabular-nums text-ink-3">
        {notice.recipient_count} người nhận · {notice.read_count} đã đọc
      </p>
    </Ticket>
  );
}

function Composer({ audiences, onClose }: { audiences: Audience[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const [choice, setChoice] = useState(audienceValue(audiences[0] as Audience));
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  const send = useMutation({
    mutationFn: async () => {
      const entry = audiences.find((a) => audienceValue(a) === choice);
      if (!entry) throw sendFailure(400, { audience: ["unknown"] });
      const { data, response, error } = await api.POST("/api/setup/notices/", {
        body: {
          audience: entry.audience,
          school_class: entry.school_class?.id ?? null,
          subject_group: entry.subject_group?.id ?? null,
          title: title.trim(),
          body,
        },
      });
      if (!data) throw sendFailure(response.status, error);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: NOTICES_KEY });
      onClose();
    },
  });
  useFocusRefused(form, send.error);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          ref={form}
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            send.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Gửi thông báo</DialogTitle>
            <DialogDescription>
              Người nhận được chốt khi gửi và nhận thông báo trong ứng dụng, kèm thư điện tử nếu có.
            </DialogDescription>
          </DialogHeader>
          <Field id="audience" label="Gửi đến" error={fieldError(send.error, "audience")}>
            <NativeSelect
              id="audience"
              value={choice}
              onChange={(event) => setChoice(event.target.value)}
              {...invalidProps(send.error, "audience")}
            >
              {audiences.map((entry) => (
                <option key={audienceValue(entry)} value={audienceValue(entry)}>
                  {audienceLabel(entry)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="title" label="Tiêu đề" error={fieldError(send.error, "title")}>
            <Input
              id="title"
              maxLength={MAX_TITLE}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              {...invalidProps(send.error, "title")}
            />
          </Field>
          <Field id="body" label="Nội dung" error={fieldError(send.error, "body")}>
            <Textarea
              id="body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              {...invalidProps(send.error, "body")}
            />
            <p
              className={cn(
                "text-xs tabular-nums text-ink-3",
                body.length > MAX_BODY && "text-destructive",
              )}
            >
              {body.length} / {MAX_BODY}
            </p>
          </Field>
          <FormError message={formMessage(send.error)} />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              Huỷ
            </Button>
            <Button type="submit" disabled={send.isPending}>
              Gửi
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
