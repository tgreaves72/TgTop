# TgTop 0.2

This release implements the roadmap’s first security, reliability, and daily-use improvements. It preserves the existing account stores and provider settings.

## Changes

- Generic record editing cannot approve workflows or change service-owned fields. Task and note sync accepts only editable fields.
- App, SMS, AI, and MCP task creation share validation. Task completion and its next recurring occurrence commit together. Monthly tasks retain their original day after February and other shorter months.
- Sync commits a change, its event, and its retry receipt together. Reusing an operation ID with different content fails. Conflicting changes still require review. Background updates fetch changes instead of downloading the whole workspace and preserve an open assistant draft.
- Phone actions and replies have separate durable states. Interrupted deterministic actions recover after restart. An uncertain reply requires provider-history review before retrying, and never repeats a successful action. Failed actions can be retried with confirmation in Connections. Twilio replies now use the outbox rather than returning message text in the webhook response.
- Reminder occurrence claims and delivery records commit together before sending.
- Optional authenticator-based two-factor login uses PyOTP, encrypted setup secrets, replay protection, and ten one-use recovery codes. Enable it in Setup & settings → Account security. Enrollment revokes other sessions. Recovery codes require the account password and cannot recover a forgotten vault password.
- Security-sensitive rate limits survive service restarts. Session routing caches a validated record reference and checks revocation on every request.
- Calendar offers month, week, and agenda views. Task entry uses the account timezone. Nonexistent daylight-saving times fail clearly; repeated autumn times use the earlier occurrence.
- Resume editing retains the latest twenty encrypted previous versions. Download a revision from Version history. Resume contents remain outside AI tools and search.
- Backups include a file-integrity manifest and restore the legacy local resume recovery copy. A private rollback journal recovers an interrupted account restore at startup. Existing TGTOP1 archives remain readable. Backups still use the bounded, in-memory archive format.
- Authorized assistant search supports Word paragraph text, weighted title matches, versioned source references, and redaction of recognizable credential patterns. Vault records remain unavailable to AI. Pattern matching cannot identify every secret in arbitrary documents; grant file access deliberately.
- Closing the Windows application keeps it in its tray for notifications. Quit through the tray menu. Optional Windows startup remains off unless enabled in settings.
- GitHub checks cover Windows and Linux, backend regressions, browser script parsing, account isolation, cloud-address validation, and timezone handling. An MIT license matches the existing package metadata.

## Validation and limits

Release verification passed 49 tests on Windows and 47 tests inside the Linux deployment image; two Windows-specific tests skipped on Linux. The packaged Windows service passed task, file, vault, encrypted-backup, and PWA checks. Browser inspection verified month, week, agenda, and account-security controls against fictional demo data. JavaScript checks verified account isolation, cloud-address validation, and timezone conversion, including daylight-saving gaps. The deployed service reports version 0.2.0 and passes its health check. Windows packaging remains unsigned.

Provider transport tests use explicit mocks. This release does not send a live verification or reminder message, initiate an AI request against the user’s plan, or enable two-factor login on the user’s behalf. Existing connections remain configured.

The wider roadmap still includes passkeys, browser push notifications when TgTop is closed, streaming backups, an off-host backup destination, per-field automatic conflict merging, cloud-to-PC resume writeback, broader document extraction, a separately enrolled device agent, and signed Windows updates. These features are not claimed by 0.2. The present backup workflow remains restricted to an encrypted download by an approved application session. Always Free hosting can become unavailable or reclaim idle resources; keep an independent encrypted backup. No paid service or hosting upgrade is part of this release.

Authenticator implementation follows [PyOTP’s replay and throttling guidance](https://pyauth.github.io/pyotp/) and [OWASP’s MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html).
