# Current release

See [TgTop 0.2](RELEASE-0.2.md) for current behavior and remaining work. The sections below record earlier implementation stages and their verification at that time.

# TgTop delivery report

October 11, 2026 · Functional early release 0.1.0

Default appearance: blue highlights and branding, with a matching navy dark mode. Existing light/dark preferences are preserved.

## Implemented

| Stage | Delivered behavior |
|---|---|
| 1. Core | Task-first dashboard; personal/school/work projects; files, folders, tags, notes, task links, searchable metadata; due dates, priority, subtasks, dependencies, recurrence, and completion. |
| 2. Vault and recovery | Separately encrypted credential vault, explicit unlock, five-minute expiry, masked values, encrypted backups, integrity-checked restore, export, recoverable trash. Windows service key protected with DPAPI. |
| 3. Reminders | Persistent scheduler, timezone/DST handling, quiet hours, recurrence, snooze, desktop delivery queue, SMS outbox, provider-status reconciliation, uncertain-dispatch review. |
| 4. AI and Codex | OpenAI Responses API adapter with structured permission-checked tools; clearly labeled local-search simulator; official MCP SDK stdio bridge; visible sources/action history; inherited source-consent checks for conversation history. |
| 5. SMS | Twilio Verify onboarding; signed webhooks; verified sender checks; five-minute provider freshness check; durable message deduplication; bounded command grammar; app approval for backups; labeled development simulator. |
| 6. Devices and delivery | Shared authenticated API/event stream, versioned edits and conflict resolution, encrypted opt-in offline task/note queue, device enrollment/revocation, responsive PWA, Electron shell, Windows packaging pipeline, Docker/Caddy hosting examples. |

## Calendar resume and messaging update

Task navigation opens an interactive month calendar with existing task entries, day-to-task creation, month navigation, undated tasks, and overdue tasks. Resume replaces the main Notes page while retaining project notes. It edits paragraph text in an approved original DOCX file, preserves other Word parts and run styles, rejects stale revisions, stores an encrypted previous-save copy, and requires confirmation before recovery/discard. The actual Desktop resume was linked privately and compatibility checked in memory; its file contents were not changed. Browser QA saved and restored edits in a fictional test file and verified the disk contents. The rebuilt frozen service also passed original-file resume save/restore, messaging setup routes, calendar asset checks, and persistent account/task checks across two restarts.

Photon and Twilio can be configured through a secure masked setup form. Photon uses the official Advanced iMessage HTTP Proxy and Photon Webhook bridge; it requires an account with SMS access and a hosted server, not just Spectrum project keys. New tests verify encrypted/redacted settings, actual adapter request shape with mocked transport, private phone verification, signed incoming command execution, and stale/duplicate rejection. **No live Photon or Twilio message has been sent or received.** See MESSAGING.md for the remaining provisioning and hosting steps.

![Calendar with fictional QA tasks](calendar-preview.png)

## Windows storage isolation repair

Windows app-container redirection can make Store Python and native executables see different AppData key files. Application records now use `%USERPROFILE%\.tgtop\data`, outside those redirected folders. Chromium profile settings still use AppData. Before migration, TgTop copies legacy stores into private recovery folders, validates their ciphertext against their key, and preserves existing accounts and records. It blocks migration when a legacy account cannot be decrypted or multiple distinct accounts conflict. Existing recovery archives remain intact. On this PC, the active legacy stores contain private phone/resume settings and no registered account; no password was chosen or account created on the user’s behalf. Independent native Python and Store Python both read the same retained settings in the new location. A frozen-service test also verified that source Python could read its account/task and write a note visible to the native service, followed by two successful native restarts.

## Account persistence repair

By default, all Windows launch methods use `%USERPROFILE%\.tgtop\data`, independent of the current folder. The desktop profile is fixed and duplicate launches focus the existing window. The service publishes its encryption key atomically once, and reopening never rewrites it. Login sessions persist for seven days; signing out does not erase records. Sign-up cannot replace an existing account. A decryption failure shows a recovery error rather than new-account setup. The updated NSIS installer completed with exit code 0. The installed application displays the new Sign up / Log in interface; a second desktop launch reuses the original window and one service. The user authorized replacing the unreadable test workspace; its original files are retained in a `data-recovery-*` folder beside the permanent data directory.

## Verification

Twenty-four automated tests pass in a clean Python environment. They exercise actual application routes, SQLite persistence, encryption, and backup contents. Provider calls use explicit mocks; they are not live provider verification.

| Required workflow | Result |
|---|---|
| Project → file upload → linked task | Passed; original download matches; stored blob is encrypted. |
| Authorized assistant context search | Passed; project/file consent checked; revoked file sources also exclude derived conversation history. Browser search displays source references and simulator label. |
| Account reopening | Passed sign-up, persistent session, two actual frozen-service process restarts, sign-out/login, and retained tasks. Existing key bytes remain unchanged; concurrent first-launch creation checked. |
| Vault lock/unlock | Passed; incorrect master password rejected; locked saving/revealing blocked; expiry checked; secrets absent from app-state/context output. |
| SMS reminder send/receive | Provider adapter send and signed incoming command tested with mocked Twilio. **No live SMS was sent or received.** |
| Task from verified incoming SMS | Passed with mocked real-provider message and signature; simulator onboarding/commands also tested. |
| Reject unauthorized/repeated/stale commands | Passed; invalid signature, unauthorized sender, duplicate MessageSid, old provider timestamp, and rate limit checked. |
| Reminder restart durability | Passed with a second database connection, duplicate dispatch prevention, desktop acknowledgement, and interrupted-dispatch recovery. |
| Two-device sync and conflict resolution | Passed with two independent authenticated clients; stale proposal returns current version; merged edit becomes visible to the other client; repeated operation does not repeat its mutation. |
| Backup and restore | Passed; wrong password rejected; task/file/vault restored; vault still needs master password; sessions revoked; pre-restore snapshot preserved. |
| Codex MCP protocol | Passed actual stdio initialize, tool listing, and authorized context tool call against the isolated local demo service. No live Codex task was started. |
| Live AI tool-loop adapter | Passed with a mocked OpenAI SDK response and function-call loop; `store=False` and strict schemas verified. **No live AI call was made.** |
| Browser UI | Task created and completed through interface; assistant context search verified; desktop (1440×960) and phone (390×844) layouts inspected. |
| Restricted backup workflow | Passed: run blocked before app approval, then encrypted output produced and run marked completed. |

The frozen Windows service also passed task creation/completion, file upload/download, vault save/reveal/lock, encrypted backup, and PWA asset checks. The NSIS installer completed with exit code **0**. The installed application launched from `%LOCALAPPDATA%\Programs\tgtop\TgTop.exe`, started its packaged service, and displayed the account setup screen; verified through Windows accessibility and screenshot inspection. Your private phone setting is present and unverified. No account or vault master password was chosen on your behalf.

Installer: `release/TgTop Setup 0.1.0.exe` · 199,294,476 bytes · unsigned.

SHA-256: `b44057b3cd83e3bc5958283c6be75795d38a95c6d67c162fe29c91a42431c424`.

`npm audit` reports zero vulnerabilities. Python dependency consistency, JavaScript syntax, twenty-six automated tests, actual MCP protocol smoke test, and frozen-service checks passed. Live-provider messages, real OpenAI responses, OS notification display, physical second-device/offline browser operation, and macOS/Linux installation have not been verified here. The tests cover two independent device sessions and API conflicts rather than claiming physical-device testing.

![Desktop interface with fictional QA data](desktop-preview.png)

## External setup required

- OpenAI API account/project key and an available configured model for generative AI. Codex connects separately through its supported MCP configuration and its own account.
- Twilio account, SMS-capable sender, Verify service, private provider secrets, public HTTPS webhook, and **real** phone ownership verification for live SMS.
- Always-on HTTPS hosting and persistent private storage for SMS while this PC is off and for shared multi-device data. No cloud service has been deployed or provisioned.
- Code-signing certificate for a signed Windows installer. Future macOS/Linux builds require native platform packaging/testing.

Provider API usage, SMS messages, verification, number rental, hosting, and optional code signing have external costs; no free allowance is assumed.

## Current limits

- Separate username-based accounts, one service process. No shared-workspace collaboration, team roles, MFA, passkeys, background web push, or independently audited production security certification.
- Devices sync through a common service. Separate local installations do not automatically federate. Offline task/note edits are queued only after the user enables and unlocks local encrypted storage; there is no offline file/vault cache.
- Text previews and bounded text-file retrieval are implemented. Images/PDFs and binary documents can be downloaded; OCR and rich document extraction are not implemented.
- The local workflow allowlist contains encrypted service backup only. There is no general-purpose remote PC agent, arbitrary shell automation, or automatic vault-backed AI credential grant.
- SMS natural-language support is a documented, bounded grammar. Ambiguous commands ask for clarification. Only generic notices and counts leave through SMS.
- Provider outcome uncertainty requires manual review before retry; this avoids blindly sending duplicates. Exactly-once network delivery is not claimed.
- Native notifications require the Windows app to be running; browser notifications require an active page and permission. Missed reminders remain visible after reconnect.
- Vault recovery cannot bypass a forgotten master password. Offline, vault, account, and backup password responsibilities are explained in Setup and SECURITY.md.

## Photon Spectrum update, October 12, 2026

The Photon TgTop project was created on the Free shared iMessage/RCS plan. The current dashboard supplies Spectrum credentials, so a new adapter uses the official Stable @spectrum-ts/core and @spectrum-ts/imessage SDKs. The encrypted project secret passes over private process pipes, never command-line arguments or AI context. SDK telemetry is disabled. Incoming authenticated stream commands require a live-verified recipient, fresh timestamp, bounded text, rate limit, and durable deduplication. Twenty-seven tests pass and npm audit reports zero vulnerabilities. The saved encrypted credentials authenticated successfully. The recipient is active in Photon. Initial sends returned gRPC permission denied (code 7). After the user sent an incoming routing message, TgTop completed real-code verification and shows Verified (live). Carrier SMS transport and reminder delivery receipts have not been independently verified. This update does not claim carrier SMS delivery.

The Spectrum Windows backend and bundled SDK are installed and import successfully. TgTop reopened with its existing signed-in account and its Photon setup form. Its project ID and encrypted project secret are saved. A callable-provider binding defect was corrected and covered by a regression test. The shared line initially denied outbound messaging. The user sent an incoming routing message, and the authenticated app now reports the phone as live verified. No credentials or verification codes were exposed during diagnostics.

## ChatGPT plan and Photon AI integration

The local Windows application now implements official app-owned dynamic OAuth registration with PKCE, state, nonce, signature/issuer/audience validation, encrypted multi-account token storage, serialized refresh, disconnect/revocation, and a live model picker. ChatGPT Responses requests use store=false and stream=true and require completion. Phone messages prefixed AI use structured intent planning, project permission checks, fixed acknowledgments, and existing verified-sender/deduplication protections. All 31 tests pass. Live account authorization and model selection succeeded. The installed Windows assistant displayed a real ChatGPT reply with the expected connection verification text, and account authorization/model selection survived restart; a real structured phone-intent request returned an authorized task count without changing workspace data. Streaming output-item reconstruction fixes providers that leave the terminal response output empty. The connection panel now refreshes automatically after browser consent. End-to-end AI commands sent through the phone still require a real incoming-message check; this report does not claim that test passed.


## Separate accounts

Login requires a username and password. Local sign-up creates an independent encrypted database, managed-file directory, vault, settings, connections, events, and reminder queue. Request-local account selection protects concurrent requests, MCP sessions, OAuth callbacks, backups, and restores. Existing single-owner data stays in place with its current password and sessions; migration registers a username from the existing name. Offline caches and pending edits use per-service/per-username keys; the original owner can migrate a legacy encrypted cache after authenticated login. External PC files remain restricted to the device owner's approval. New users configure their own Photon and ChatGPT connections, and one verified phone belongs to one account. Remote registration defaults to disabled.

Verification: all 35 tests passed, including migration of an existing account and sessions, concurrent account isolation, file/vault access rejection, password changes and revocation, and account-scoped backups/restores/reminder processing.

The rebuilt Windows backend passed two-user packaged checks, cross-account write rejection, two process restarts, saved task persistence, and resume save/restore in isolated QA data. The installed application reopened with the original session, 24 saved records, its ChatGPT connection, and verified Photon phone intact. The existing account now uses username tyler with its original password.

A separate UI isolation check passed: delayed responses from the previous account are rejected before their contents reach the UI, sign-out clears cached resume/chat context, and offline storage keys differ by user.

Final multi-user installer SHA-256: b44057b3cd83e3bc5958283c6be75795d38a95c6d67c162fe29c91a42431c424; 175986306 bytes. Embedded account UI matches the source.

## Shared cloud account connection

Added cloud connection before login and in Connections, current-service/last-check indicators, validated HTTPS service switching, persistent desktop destination settings, and return-to-local recovery. Local accounts remain intact; encrypted backup/restore provides explicit migration. Docker/Caddy deployment now supplies the Photon Node runtime, persistent storage, backend health checks, one public HTTPS entry point, and initial account provisioning. All 36 Python tests plus account UI and cloud connection checks passed. The independent-device test covers file/task sharing, durable duplicate edits, stale conflicts, reviewed updates, and isolated session revocation. No cloud host has been provisioned; Docker execution and physical second-PC operation remain unverified.

Current cloud-capable installer: 175987401 bytes; SHA-256 29e3fe7e58122daf0a51000dbda6f4df5d71eafe77e34107802f74cc55fedb6b. The updated installed desktop opened its saved account and displayed the real cloud connection form, with existing ChatGPT and verified Photon connections intact.
