import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type LeaveRequest = components["schemas"]["LeaveRequest"];
export type LeaveStatus = LeaveRequest["status"];

/** Every leave request key starts here, so one invalidation refreshes them all. */
export const LEAVE_KEY = ["leave-requests"] as const;

/** The requests the member may see, newest first; `status` narrows them. */
export const leaveRequestsQuery = (status?: LeaveStatus) =>
  queryOptions({
    queryKey: [...LEAVE_KEY, status ?? "all"],
    queryFn: () =>
      ok(
        api.GET("/api/setup/leave-requests/", { params: { query: status ? { status } : {} } }),
        "leave requests",
      ),
  });

/** The students the member may send a request for (the Guardian's children). */
export const leaveChildrenQuery = queryOptions({
  queryKey: [...LEAVE_KEY, "children"],
  queryFn: () => ok(api.GET("/api/setup/leave-requests/children/"), "leave children"),
});
