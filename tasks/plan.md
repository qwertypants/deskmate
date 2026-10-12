# Plan: Enforce a Single Animation During Meetings

## Goal

Make the in-meeting AWTRIX screen show only `deskmate-wave` in the app loop, and make failures to establish that state visible instead of reporting success.

## Current finding

`src/awtrix_takeover.py:claim()` already requests an exclusive loop with `set_app_order([owner], disabled_names)`. `src/meeting_mode.py:enter()` then reads the app list, but `verified()` only checks that `deskmate-wave` is present, enabled, in the loop, and error-free. It does not verify that other apps left the loop. That leaves a readback/diagnostic gap; a live device readback is needed to confirm whether AWTRIX is actually retaining extra apps.

## Scope and preservation boundaries

- Change only the meeting-mode enforcement and its focused coverage in `src/meeting_mode.py`, `tests/test_meeting_mode.py`, and the meeting-path fixtures in `tests/test_calendar_widget.py`.
- Preserve the existing Great Wave Berry source, its seven-second animation cycle, and the Calendar rule that enters meeting mode after a successful fetch detects an ongoing event.
- Preserve takeover snapshots, brightness handling, restore behavior, state files, and app ownership safeguards.
- Leave `src/awtrix_takeover.py`, `src/idle_mode.py`, `src/calendar_widget.py`, other widgets, and all non-meeting app behavior unchanged unless investigation proves a meeting-specific dependency requires a narrowly scoped adjustment.
- Do not alter or overwrite the existing Great Wave design/implementation plan.

## Implementation steps

### 1. Make meeting verification enforce exclusivity

Update the meeting-mode readback predicate so success requires `deskmate-wave` to be present, script-owned, enabled, error-free, and in the loop, and requires every other reported app to be out of the active loop. Include unexpected loop-member names in the failure message so the device response identifies what remained active.

Keep the exclusivity check local to meeting mode. The shared takeover helper is also used by overnight idle mode, so changing its behavior would broaden this repair unnecessarily.

### 2. Reassert the meeting loop when readback is not exclusive

If the first post-takeover readback shows additional active loop members, issue the same meeting-specific order/disable request once more, activate `deskmate-wave`, and read back again. If the second readback is still not exclusive, fail the run with the unexpected app names; do not claim the meeting screen is verified. Keep this bounded so a persistent device/API problem is visible and does not create an unending retry loop.

### 3. Cover the meeting behavior

Extend `tests/test_meeting_mode.py` and adjust the meeting-path fixtures in `tests/test_calendar_widget.py` for:

- A successful readback where the wave is the sole active loop member.
- A first readback containing another active app, followed by a successful reassertion/readback.
- A persistent extra loop member, which must raise a clear error naming that app.
- Preservation of existing install, collision refusal, idle takeover, and restore expectations.
- Calendar integration fixtures provide the AWTRIX device/app readback required by meeting takeover and model the disabled Calendar app after entry; Calendar production behavior stays unchanged.

Do not change idle-mode tests or shared takeover behavior.

### 4. Verify on the target display

Run the focused meeting-mode tests and inspect the diff for scope. Then verify a real meeting-mode entry on the TC001: read `/api/v1/apps` after takeover and confirm `deskmate-wave` is the sole enabled loop member; observe that it continues through repeated seven-second cycles. Confirm exit restores the saved app loop and brightness. Treat test or HTTP acknowledgement alone as insufficient evidence of the physical display state.

## Acceptance criteria

- During meeting mode, readback confirms `deskmate-wave` is the only enabled app with `inLoop: true`.
- A non-exclusive first response is reasserted once; persistent non-exclusivity is reported as a failure with app names.
- Meeting entry and exit continue to preserve the original loop and brightness.
- Calendar selection, other widgets, idle mode, and the Great Wave animation asset are unchanged.

## Risks and limits

- The prior code established that exclusivity was requested, not that the device applied it. The actual cause remains unconfirmed until the TC001 readback is observed.
- AWTRIX could report stale or inconsistent `enabled`/`inLoop` fields. Keep error details tied to the returned app list and report that state without silently claiming success.

## Execution status

- Meeting-mode and Calendar-path fixtures now cover sole-loop success, one bounded reassertion, and persistent extra loop members.
- Focused meeting-mode tests pass (10 tests); the full repository suite passes (125 tests) using `.venv`.
- TC001 runtime readback remains unverified because this host has no route to the configured AWTRIX address and no `CODEX_SSH_HOST` is configured. No device state was changed.

## Task list

See `tasks/todo.md` for the ordered checklist.
