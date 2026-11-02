# Slice 8: Frontend shell

Slice 8 of `docs/phase-0.md`. Standing rules: `DESIGN.md` (locked; § Login, § Controls, § Dark mode), `docs/tech-stack.md` (API client), ADR 0003 (same-origin session auth), the prototype's login screen (branch `prototype/core-screens`, `prototype/index.html` § 1). Slice 1 already ships tokens, base styles, both modes, the shadcn primitives and a placeholder `AppShell`.

Done when the prototype's login screen works against the API: on `a.localhost` it shows the School's name, signs a member in, lands on the home route with the top bar naming the School and the person, and signs out; a Guardian activates an invite code the same way; a wrong password and a wrong code each show one Vietnamese message.

## API client

- Types from `openapi-typescript`, calls through `openapi-fetch` (typed `fetch`, ~6 kB, same author); no hand-written request types.
- The schema is committed as `frontend/src/api/openapi.json`, its types as `frontend/src/api/schema.d.ts`; `make api-client` regenerates both. The OpenAPI diff check (`docs/tech-stack.md` § CI) is a backend test that fails when the committed schema differs from the generated one, and `make frontend-check` fails when `schema.d.ts` is stale. A schema change therefore shows up in review.
- CSRF: the client reads the CSRF cookie (`csrftoken`, `__Host-csrftoken` behind HTTPS) and sends `X-CSRFToken` on every unsafe request; it calls `GET /api/auth/csrf/` once when no cookie exists yet. Django rotates the token at login, so the cookie is read per request, never cached.

## Backend additions

- `GET /api/auth/school/` (AllowAny): the host's School `{name, subdomain}`, so the login screen can lead with it before anyone signs in. Nothing else about the School is public.

## Routes

English paths (CLAUDE.md), Vietnamese copy.

- `/login`, `/activate`: outside the shell; the host and the School name lead, one form each (DESIGN.md § Login). After success: the `redirect` search param, else `/`.
- Signed-in layout (pathless `_app`): loads `me` before rendering; a 401 or 403 redirects to `/login?redirect=<path>`. The top bar shows the School name, navigation, the person's name, the mode toggle and Đăng xuất.
- Later screens as placeholders inside the layout, each with its empty state: `/` (teacher home), `/gradebook`, `/students/$studentId`, `/guardian`.

## Decisions

- **No password reset in the MVP backend**, so the prototype's "Quên mật khẩu" link becomes a note: "Quên mật khẩu? Hỏi quản trị trường của bạn." (DESIGN.md § Login).
- Errors: the API's generic errors map to one message each ("Sai số điện thoại, email hoặc mật khẩu.", "Mã mời không đúng hoặc đã hết hạn."); field errors (a weak password) sit under their field; a network failure says to try again.
- Navigation shows only links whose screens exist; capabilities gate links once screens do.
