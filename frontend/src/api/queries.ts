import { queryOptions } from "@tanstack/react-query";
import { api } from "./client";

/** Thrown when there is no signed-in member of this School (401 or 403). */
export class SignedOut extends Error {}

export const schoolQuery = queryOptions({
  queryKey: ["school"],
  queryFn: async () => {
    const { data, error } = await api.GET("/api/auth/school/");
    if (error || !data) throw new Error("school");
    return data;
  },
  staleTime: Number.POSITIVE_INFINITY,
});

export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: async () => {
    const { data, response } = await api.GET("/api/auth/me/");
    if (response.status === 401 || response.status === 403) throw new SignedOut();
    if (!data) throw new Error("me");
    return data;
  },
  retry: (count, error) => !(error instanceof SignedOut) && count < 2,
});
