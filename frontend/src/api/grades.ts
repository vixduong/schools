import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";
import { ok } from "./timetable";

export type GradebookDetail = components["schemas"]["GradebookDetail"];
export type GradebookColumn = components["schemas"]["Column"];
export type GradebookRow = components["schemas"]["Row"];
export type GradebookCell = components["schemas"]["Cell"];
export type CellInput = components["schemas"]["CellInput"];
export type CellError = components["schemas"]["CellError"];
export type CurrentEntry = components["schemas"]["CurrentEntry"];
export type MyPair = components["schemas"]["MyPair"];
export type HistoryEntry = components["schemas"]["HistoryEntry"];
export type SubjectLoad = components["schemas"]["SubjectLoad"];
export type Term = components["schemas"]["Term"];
export type Grade = components["schemas"]["Grade"];
export type GradebookStep = components["schemas"]["Step"];
export type StepAction = components["schemas"]["GradebookStepActionEnum"];
export type EmptyCell = components["schemas"]["EmptyCell"];
export type ReviewItem = components["schemas"]["ReviewItem"];

export const GRADEBOOK_KEY = ["gradebook"] as const;

/** The signed-in teacher's teaching pairs this year, each with its terms' gradebooks. */
export const myGradebooksQuery = queryOptions({
  queryKey: [...GRADEBOOK_KEY, "mine"],
  queryFn: () => ok(api.GET("/api/setup/gradebooks/mine/"), "my gradebooks"),
});

/** The submitted gradebooks this member may review, newest submit first. */
export const gradebooksToReviewQuery = queryOptions({
  queryKey: [...GRADEBOOK_KEY, "to-review"],
  queryFn: () =>
    ok(api.GET("/api/setup/gradebooks/", { params: { query: { to_review: 1 } } }), "to review"),
});

export const gradebookQuery = (id: number) =>
  queryOptions({
    queryKey: [...GRADEBOOK_KEY, id],
    queryFn: () =>
      ok(api.GET("/api/setup/gradebooks/{id}/", { params: { path: { id } } }), "gradebook"),
  });

/** Every entry of a cell, oldest first. */
export const cellHistoryQuery = (id: number, column: number, student: number) =>
  queryOptions({
    queryKey: [...GRADEBOOK_KEY, id, "history", column, student],
    queryFn: () =>
      ok(
        api.GET("/api/setup/gradebooks/{id}/history/", {
          params: { path: { id }, query: { column, student } },
        }),
        "cell history",
      ),
  });

export const termsQuery = queryOptions({
  queryKey: ["setup", "terms"],
  queryFn: () => ok(api.GET("/api/setup/terms/"), "terms"),
});

export const gradesQuery = queryOptions({
  queryKey: ["setup", "grades"],
  queryFn: () => ok(api.GET("/api/setup/grades/"), "grades"),
});

export const subjectLoadsQuery = (schoolYear: number) =>
  queryOptions({
    queryKey: ["setup", "subject-loads", schoolYear],
    queryFn: () =>
      ok(
        api.GET("/api/setup/subject-loads/", { params: { query: { school_year: schoolYear } } }),
        "subject loads",
      ),
  });
