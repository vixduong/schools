import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type LeaveRequest = components["schemas"]["LeaveRequest"];
export type LeaveStatus = LeaveRequest["status"];

/** Every leave request key starts here, so one invalidation refreshes them all. */
export const LEAVE_KEY = ["leave-requests"] as const;

/** What narrows the list: a status, `sent` (the ones the member sent: a Guardian's block) or
 * `to_decide` (the ones waiting on the member's yes, never their own: the inbox). */
export type LeaveFilters = { status?: LeaveStatus; sent?: 1; to_decide?: 1 };

/** The requests the member may see, newest first. */
export const leaveRequestsQuery = (filters: LeaveFilters = {}) =>
  queryOptions({
    queryKey: [...LEAVE_KEY, filters],
    queryFn: () =>
      ok(api.GET("/api/setup/leave-requests/", { params: { query: filters } }), "leave requests"),
  });

/** The students the member may send a request for (the Guardian's children). */
export const leaveChildrenQuery = queryOptions({
  queryKey: [...LEAVE_KEY, "children"],
  queryFn: () => ok(api.GET("/api/setup/leave-requests/children/"), "leave children"),
});
