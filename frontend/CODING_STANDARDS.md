# Frontend coding standards (for review)

Read during review, not implementation. Judgement calls no automated check covers; lint (Biome), types and the tests in `src/test/` already run in `make frontend-check`, and `make smoke` runs the app against the API. Rules came from the slice 8 review; `docs/slices/slice-8.md` holds the reasons. Design rules are `DESIGN.md`.

## API and session

- **Only a 400 is a refusal of what the person typed.** A 5xx, a CSRF 403, a 429 or a proxy's HTML page is a server or network problem and reads as one (`refusal()` in `src/lib/messages.ts`); never map an unknown status to "wrong password".
- **A state change shows only after the server confirms it.** Sign-out, and any later destructive action, leaves the screen or clears the cache on a 2xx, and says so otherwise: on a shared school computer a failed sign-out that looks done leaves a live session.
- **A signed-in screen never outlives the session.** Data of one person is cleared before another signs in (`queryClient.clear()`), and a `SignedOut` from any query sends the person to `/login` (`makeApp()` in `src/router.tsx`).
- **Every `redirect` passes `safeRedirect`.** Navigation targets from the URL resolve to this origin, or they are dropped.
- **Calls go through `api`** (`src/api/client.ts`, typed from the committed schema, CSRF handled); no bare `fetch` to `/api`.

## Forms

- **Every field error is under its field and tied to it** (`invalidProps`: `aria-invalid`, `aria-describedby`); after a refused submit, focus moves to the first refused field; a form-level message is `role="alert"`.
- **Copy is Vietnamese and addresses the reader neutrally** ("bạn"), unless the screen is only ever seen by one role.
