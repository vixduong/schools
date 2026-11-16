import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type Audience = components["schemas"]["Audience"];
export type ReceivedNotice = components["schemas"]["ReceivedNotice"];
export type SentNotice = components["schemas"]["SentNotice"];

/** Every notice list's key starts here, so one invalidation refreshes them all. */
export const NOTICES_KEY = ["notices"] as const;

/** The notices the member received, newest first. */
export const receivedNoticesQuery = queryOptions({
  queryKey: [...NOTICES_KEY, "received"],
  queryFn: async () => (await ok(api.GET("/api/setup/notices/"), "notices")) as ReceivedNotice[],
});

/** The notices the member sent, with the counts of recipients and read marks. */
export const sentNoticesQuery = queryOptions({
  queryKey: [...NOTICES_KEY, "sent"],
  queryFn: async () =>
    (await ok(
      api.GET("/api/setup/notices/", { params: { query: { sent: 1 } } }),
      "sent notices",
    )) as SentNotice[],
});

/** What the member may send to: empty for a member who may send nothing. */
export const noticeAudiencesQuery = queryOptions({
  queryKey: ["notice-audiences"],
  queryFn: () => ok(api.GET("/api/setup/notices/audiences/"), "notice audiences"),
});
