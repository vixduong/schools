/** Unsaved gradebook cells kept in this browser, so a crash or an expired session loses nothing.
 * One entry per member and gradebook (an Account has one Membership per School, and the host is the
 * School). A cell leaves the draft when the server confirms it; a draft untouched for a week is
 * dropped; an explicit sign-out removes the member's drafts (school computers are shared). */
export type DraftEdit = { text: string; expected: number | null }; // typed text; the entry last seen

const PREFIX = "gradebook-draft";
export const DRAFT_LIFETIME_MS = 7 * 24 * 60 * 60 * 1000;

const prefixOf = (account: number) => `${PREFIX}:${location.host}:${account}:`;
export const draftKey = (account: number, gradebook: number) => `${prefixOf(account)}${gradebook}`;

/** The saved edits, or null when there is none, it is older than a week, or it is unreadable. */
export function readDraft(key: string): Record<string, DraftEdit> | null {
  try {
    const stored = JSON.parse(localStorage.getItem(key) ?? "null") as {
      at?: unknown;
      edits?: Record<string, { text?: unknown; expected?: unknown }>;
    } | null;
    if (!stored) return null;
    if (typeof stored.at !== "number" || Date.now() - stored.at > DRAFT_LIFETIME_MS) {
      localStorage.removeItem(key);
      return null;
    }
    const edits: Record<string, DraftEdit> = {};
    for (const [cell, edit] of Object.entries(stored.edits ?? {})) {
      const { text, expected } = edit;
      if (typeof text === "string" && (expected === null || typeof expected === "number"))
        edits[cell] = { text, expected };
    }
    return Object.keys(edits).length ? edits : null;
  } catch {
    return null;
  }
}

/** Keep `edits` as the draft; none left removes it. Storage that is full or off is no error: the
 * draft is a safety net. */
export function writeDraft(key: string, edits: Record<string, DraftEdit>) {
  try {
    if (Object.keys(edits).length === 0) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify({ at: Date.now(), edits }));
  } catch {
    // nothing to do: the draft is a safety net
  }
}

function draftKeysOf(account: number): string[] {
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(prefixOf(account))) keys.push(key);
  }
  return keys;
}

/** How many cells this member has waiting in drafts, in every gradebook. */
export function countDrafts(account: number): number {
  return draftKeysOf(account).reduce(
    (sum, key) => sum + Object.keys(readDraft(key) ?? {}).length,
    0,
  );
}

/** Every draft of the member on this browser (an explicit sign-out). */
export function clearDrafts(account: number) {
  for (const key of draftKeysOf(account)) localStorage.removeItem(key);
}
