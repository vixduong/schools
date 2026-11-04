import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type Sheet = components["schemas"]["Sheet"];
export type SheetStudent = components["schemas"]["SheetStudent"];
export type Status = components["schemas"]["AttendanceStatusEnum"];
export type ClassAttendance = components["schemas"]["Overview"];

/** The class list of a held period on a date, each student with their mark or null. */
export const sheetQuery = (entry: number, on: string) =>
  queryOptions({
    queryKey: ["attendance", "sheet", entry, on],
    queryFn: () =>
      ok(
        api.GET("/api/setup/attendance/{entry}/{on}/", { params: { path: { entry, on } } }),
        "sheet",
      ),
  });

/** A class's late and absent marks from `from` to `to` (at most 31 days). */
export const classAttendanceQuery = (schoolClass: number, from: string, to: string) =>
  queryOptions({
    queryKey: ["attendance", "class", schoolClass, from, to],
    queryFn: () =>
      ok(
        api.GET("/api/setup/classes/{id}/attendance/", {
          params: { path: { id: schoolClass }, query: { from, to } },
        }),
        "class attendance",
      ),
  });
