import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";

export type BellPeriod = components["schemas"]["BellPeriod"];
export type MyPeriod = components["schemas"]["MyPeriod"];
export type TimetableEntry = components["schemas"]["TimetableEntry"];

export async function ok<T>(request: Promise<{ data?: T }>, what: string): Promise<T> {
  const { data } = await request;
  if (!data) throw new Error(what);
  return data;
}

/** The signed-in member's periods today (the server's date), morning first. */
export const myPeriodsQuery = queryOptions({
  queryKey: ["timetable", "mine"],
  queryFn: () => ok(api.GET("/api/setup/timetable/mine/"), "my periods"),
});

export const yearsQuery = queryOptions({
  queryKey: ["setup", "school-years"],
  queryFn: () => ok(api.GET("/api/setup/school-years/"), "school years"),
});

export const classesQuery = queryOptions({
  queryKey: ["setup", "classes"],
  queryFn: () => ok(api.GET("/api/setup/classes/"), "classes"),
});

export const subjectsQuery = queryOptions({
  queryKey: ["setup", "subjects"],
  queryFn: () => ok(api.GET("/api/setup/subjects/"), "subjects"),
});

export const roomsQuery = queryOptions({
  queryKey: ["setup", "rooms"],
  queryFn: () => ok(api.GET("/api/setup/rooms/"), "rooms"),
});

export const roleAssignmentsQuery = queryOptions({
  queryKey: ["setup", "role-assignments"],
  queryFn: () => ok(api.GET("/api/setup/role-assignments/"), "role assignments"),
});

export const membershipsQuery = queryOptions({
  queryKey: ["setup", "memberships"],
  queryFn: () => ok(api.GET("/api/setup/memberships/"), "memberships"),
});

export const bellPeriodsQuery = (schoolYear: number) =>
  queryOptions({
    queryKey: ["timetable", "bell-periods", schoolYear],
    queryFn: () =>
      ok(
        api.GET("/api/setup/bell-periods/", { params: { query: { school_year: schoolYear } } }),
        "bell periods",
      ),
  });

/** The class's entries in force today. */
export const classTimetableQuery = (schoolClass: number) =>
  queryOptions({
    queryKey: ["timetable", "class", schoolClass],
    queryFn: () =>
      ok(
        api.GET("/api/setup/classes/{id}/timetable/", { params: { path: { id: schoolClass } } }),
        "class timetable",
      ),
  });
