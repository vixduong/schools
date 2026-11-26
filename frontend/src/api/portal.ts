import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type Child = components["schemas"]["Child"];
export type ChildPeriod = components["schemas"]["ChildPeriod"];
export type ChildGradebook = components["schemas"]["ChildGradebook"];

/** Every portal key starts here, so one invalidation refreshes them all. */
export const PORTAL_KEY = ["portal"] as const;

/** The member's children: their own student record and the students linked to them. */
export const childrenQuery = queryOptions({
  queryKey: [...PORTAL_KEY, "children"],
  queryFn: () => ok(api.GET("/api/portal/children/"), "children"),
});

/** The child's periods on the School's day, with the child's mark per period. */
export const childDayQuery = (id: number) =>
  queryOptions({
    queryKey: [...PORTAL_KEY, "today", id],
    queryFn: () =>
      ok(api.GET("/api/portal/children/{id}/today/", { params: { path: { id } } }), "child day"),
  });

/** The child's released scores of the term in force, per gradebook. */
export const childScoresQuery = (id: number) =>
  queryOptions({
    queryKey: [...PORTAL_KEY, "scores", id],
    queryFn: () =>
      ok(
        api.GET("/api/portal/children/{id}/scores/", { params: { path: { id } } }),
        "child scores",
      ),
  });
