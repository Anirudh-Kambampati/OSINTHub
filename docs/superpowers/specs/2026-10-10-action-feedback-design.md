# Action Feedback Layer — Design

**Date:** 2026-10-10
**Status:** Approved in brainstorming; pending written-spec review
**Scope:** Frontend only (no backend changes)

## Problem

Every react-query mutation in the console handles `onSuccess` only — there is **no `onError`
anywhere** and no notification system (0 matches for toast/notification patterns). Consequences:

- A failed note save, decision, user create, or password change fails **silently**; the user sees
  nothing and assumes success (or confusion).
- Successful actions are equally invisible: input clears, view navigates, no confirmation.
- Password change on a wrong current password (403) currently does nothing at all.

## Goal

A complete, consistent feedback layer: **every mutation visibly reports success or failure**, with
inline states where a toast does not fit, and destructive actions confirmed first.

## Approach

Hand-rolled (Approach A, approved): ~120–150 lines of owned UI, **zero new dependencies**,
consistent with the project's existing hand-rolled primitives (`ui/primitives.tsx`, `ui/Drawer.tsx`).

## Components & files

| File | Purpose |
|---|---|
| `context/FeedbackContext.tsx` | `FeedbackProvider` mounted at app root; owns toast queue state (max 3), dedupe, auto-dismiss timers |
| `components/ui/Toast.tsx` | Toast viewport: two persistent live regions + toast item (icon, message, dismiss button) |
| `components/ui/ConfirmDialog.tsx` | Destructive-action confirmation; focus trap, focus return to trigger |
| `lib/feedback.ts` | `mapApiError(error)` — HTTP status/retry-after → human message; message-copy helpers |
| `context/FeedbackContext.tsx` (hooks) | `useFeedback()` → `{ notify, notifyError }`; `useActionFeedback(config)` → wraps a mutation, maps outcome. Both exported from this file. |

Public hook surface:

```ts
const { notify } = useFeedback();
notify("success" | "error" | "info", message);

const action = useActionFeedback(mutationConfig, {
  success: "Note added",          // shown on settle-ok
  error: "Couldn't save the note", // fallback when mapApiError has no better text
});
// returns { ...mutation, submit } — submit() runs mutateAsync with feedback applied
```

## Data flow

```
component → useActionFeedback(mutation) → settle
    ├─ ok   → notify("success", successCopy)
    └─ err  → mapApiError(err, fallbackCopy) → notify("error", text)
                └─ 401 → assertive toast + navigate("/login")
```

`mapApiError` status mapping:

| Status | Behavior |
|---|---|
| 401 | Assertive "Session expired — sign in again." + redirect to `/login` |
| 403 / 422 | Show the server's fixed `detail` (e.g. "Current password is incorrect.") — server strings are constants, safe to display |
| 429 | "Too many attempts — try again in {Retry-After} seconds." (fallback: "try again shortly") |
| 5xx | "The server had a problem — try again in a moment." |
| Network / timeout | "Can't reach the server — check your connection." |
| Other | The `error` fallback copy passed by the caller |

Belt-and-suspenders: a global `QueryClient` `queryCache`/`mutationCache` `onError` catches
unhandled 401s from background queries beneath the hook.

## Coverage map

| Action | Feedback |
|---|---|
| Login failure | Inline `FormError` (already present; standardized) |
| First-run register | Inline error + success toast "Account created — you're the administrator." |
| Create investigation (`SearchBar`) | Error toast (classify failures, 429); success stays the existing navigation to the new investigation |
| Re-run / search in investigation | Inline `RunProgress` for progress; error toast on immediate failure |
| Add note | Toast "Note added." / error toast, input preserved |
| Delete note | Toast "Note deleted." (no confirm — low stakes) |
| Decision confirm / reject / clear | Toast "Profile confirmed." / "Profile rejected." / "Decision cleared." |
| Delete investigation | **ConfirmDialog** first ("…this can't be undone"), then success toast + existing navigate; failure toast |
| Password change (Settings) | **Inline FormError on failure (fixes the silent 403)** + success toast; existing forced-logout navigation kept |
| Create user (Settings) | Toast "User created." / inline error (422 rules, duplicate email) |
| Toggle user role / active | Toast "Role updated." / "Access updated." ; error toast |
| Exports (JSON/CSV/report) | Out of scope by design: plain `<a href>` downloads keep browser-native feedback (documented boundary) |

## Copy rules

- Sentence case, plain verbs, no filler, no apologies.
- The action's own vocabulary is echoed: button "Save note" → toast "Note saved."
  Button "Confirm" → toast "Profile confirmed."
- Errors say **what happened and what to do**; never a vague "Something went wrong" when the
  status or server detail is known.
- Toasts describe outcomes in the past tense; ongoing work is described inline (RunProgress),
  not as a toast.

## Toast behavior

- Success 4 s, info 5 s, error 8 s auto-dismiss; timer pauses on hover/focus.
- Max 3 visible; adding a 4th dismisses the oldest. Identical message replaces the existing one
  (dedupe).
- Position: bottom-right on desktop, top-center on small screens.
- Errors persist longer than successes; every toast has a dismiss button.

## Accessibility

- **Two persistent live regions** (never swapped out): success/info in `aria-live="polite"` +
  `role="status"`; errors in `aria-live="assertive"` + `role="alert"`.
- Toasts **never move focus** (non-modal). `ConfirmDialog` traps focus and returns it to the
  trigger on close.
- Dismiss button `aria-label="Dismiss notification"`.
- `prefers-reduced-motion: reduce` disables enter/exit animation.
- Errors use icon **and** text — never color alone.
- Viewport labelled "Notifications".

## Edge cases

- Rapid duplicate actions → dedupe (see above); queue capped at 3.
- Session expiry during a background query → global 401 handler path.
- Investigation run failures remain **inline** (status chip + RunProgress), not toasts — they are
  states of ongoing work, not action outcomes.
- Offline: network-error copy covers it; no separate connectivity listener (YAGNI).

## Testing

- `feedback.test.tsx` (vitest + Testing Library, fake timers): toast renders into the correct
  live region, auto-dismiss timing, max-3 cap, dedupe, dismiss button.
- `feedback.test.ts` unit tests for `mapApiError`: every status branch, Retry-After parsing.
- Integration: `NotesPanel` mutation failure → error toast appears and input is preserved;
  success → "Note added." and input clears.
- `ConfirmDialog`: confirm runs the action, cancel does not, focus returns to trigger.
- Existing 18 frontend tests stay green; backend untouched; CI runs the whole matrix.

## Non-goals

- No toast library or other new dependency.
- No optimistic updates (explicitly deferred — approved scope was the complete feedback layer
  without optimistic flow).
- No undo system.
- No backend/API changes.
- No export-button refactor.
