import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Me = components["schemas"]["Me"];
export type School = components["schemas"]["School"];

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// `__Host-csrftoken` behind HTTPS, `csrftoken` in plain-http dev (backend settings). Read per
// request: Django rotates the token at login.
function csrfToken(): string | undefined {
  return document.cookie.match(/(?:^|;\s*)(?:__Host-)?csrftoken=([^;]+)/)?.[1];
}

const csrf: Middleware = {
  async onRequest({ request }) {
    if (!UNSAFE.has(request.method)) return request;
    if (!csrfToken()) await fetch("/api/auth/csrf/", { credentials: "same-origin" });
    const token = csrfToken();
    if (token) request.headers.set("X-CSRFToken", token);
    return request;
  },
};

// Same origin as the API (ADR 0003): the session cookie rides along, no tokens in JS.
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin, // absolute, as `Request` outside a browser requires
  credentials: "same-origin",
  fetch: (request) => globalThis.fetch(request),
});
api.use(csrf);

/** The API's 400 body: field name (or `non_field_errors`) to messages. */
export type FieldErrors = Record<string, string[] | undefined>;
