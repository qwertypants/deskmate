# Meeting Loop Exclusivity Checklist

- [x] Update meeting-mode readback to require the wave as the sole enabled loop member and report extra members.
- [x] Reassert the meeting app order once when the first readback is not exclusive; fail clearly if the second readback still is not exclusive.
- [x] Extend focused meeting-mode coverage while preserving existing entry, ownership, and restore expectations.
- [x] Run focused and full tests and inspect the changed-file scope.
- [ ] Verify app-loop readback and animation cycling on the TC001, then confirm saved state restoration on exit.

The TC001 readback could not be completed from this host: the configured device address returned `No route to host`, including on the approved read-only attempt. `CODEX_SSH_HOST` is not configured, so there is no known Pi route available in this environment. No device state was changed.
