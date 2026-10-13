# TgTop

A working personal workspace for tasks, project files, notes, reminders, and encrypted credentials. Windows desktop first, with a responsive installable web interface. Users sign in with unique usernames and passwords. Each account has its own private workspace; authorized devices use the same service to access that account. Shared projects and team roles are not implemented.

## Start

Canvas, Outlook, and Gradescope deadline connection options live under **Connections & devices → School connections**. New items enter review before becoming calendar tasks. Approved source changes refresh on the backend, with conflict handling and duplicate prevention. Gradescope uses Canvas-linked assignments or manual CSV/ICS schedules; it has no direct public API. Microsoft sign-in requires an Entra application registration. See [school connection setup and limitations](docs/SCHOOL-CONNECTIONS.md). These connectors are deployed to the shared cloud service; existing cloud-connected desktop installations receive them on refresh. The 0.2.0 installer’s bundled standalone backend predates this connector update; use the current source for standalone local connector support.

Install **TgTop Setup 0.2.0.exe** from `release/`, then launch TgTop. No Python installation is required by the packaged Windows app. Sign up with a unique username and a strong password. Each user gets a separate encrypted workspace. On later launches, your saved session opens the workspace; after sign-out or seven days, use Log in with that username and password. Existing single-account workspaces keep their records, password, and sessions; migration adds a lowercase username based on the existing name. Closing or updating the app does not erase your records. Your vault password is separate.

For source development, use Python 3.12 and Node 24. Run `npm ci` to install the official Photon Spectrum SDK before connecting Photon:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open `http://127.0.0.1:8765`. For the Electron development shell, stop the source service first, run `npm ci`, then `npm run desktop`. The Windows shell owns its service and stores data outside Windows app-container redirection under `%USERPROFILE%\.tgtop\data`; source mode uses the same permanent folder by default (set `TGTOP_DATA` explicitly for isolated development or hosting). Do not run two different local services on port 8765 at once.

For an isolated fictional demo, run `.\.venv\Scripts\python.exe scripts/demo.py` and open `http://127.0.0.1:8766`. Its test password is `demo-workspace-2026`. This sandbox contains no user data and is separate from your workspace. Do not expose the demo server publicly.

## Calendar, resume, and messaging update

Tasks opens a month, week, or agenda calendar with task entries, clickable dates, undated tasks, and overdue tasks. Resume replaces the general Notes page and edits text in a privately linked original Word file, with revision conflict protection and an encrypted previous-save recovery copy. Project notes are preserved. See [Resume editing](docs/RESUME.md).

Messaging can be configured privately in Connections using Photon Spectrum, the Photon HTTP bridge, or Twilio. Spectrum project credentials use an authenticated provider stream; HTTP providers require the configured HTTPS webhook. Verify phone ownership before using commands. Provider accounts and access requirements vary. See [Messaging setup](docs/MESSAGING.md). Development simulation never sends a real message.

Read the [0.2 release notes](docs/RELEASE-0.2.md) for authenticator login, recoverable phone replies, atomic sync, calendar views, resume history, and Windows background settings.

## What you can use now

- Create personal, school, and work projects; track task priorities, due dates, statuses, subtasks, dependencies, recurrence, and linked files.
- View Today, Upcoming, Overdue, All, and Done tasks; filter project workspaces; search task, file, and note metadata.
- Upload encrypted managed files up to 50 MB, organize folders and tags, link tasks, preview text, and download originals. External references are limited to configured approved folders and require that service device to remain online.
- Keep notes and project decisions, plus assistant conversation history with source IDs.
- Store vault passwords and API keys encrypted under a separately derived master key; lock, unlock, explicitly reveal, and automatically expire unlocks after five minutes.
- Schedule persistent desktop or SMS reminders, daily/weekly recurrence, quiet hours, snooze, delivery history, and manual review/retry for uncertain sends.
- Use authorized local context search without an API key. This is labeled a **development simulator**, not generative AI.
- Connect Codex through a real stdio MCP server, exposing only consented context search, task creation, and desktop reminders.
- Use authenticated SMS command simulation. Twilio live adapters implement Verify onboarding, signed incoming webhooks, provider timestamp checks, sender authorization, deduplication, and rate limits.
- Connect multiple devices to one service; queue encrypted offline task/note edits; inspect conflicting versions before replacing either; revoke device sessions.
- Create encrypted backups, restore snapshots, export non-vault JSON, move records to recoverable trash, and restore them.
- Approve, run, or cancel the restricted backup workflow. Its action runs on the **service device**, with a 30 second response limit. There is no arbitrary command runner.

## Guided setup

1. **Account and storage:** Create your local account. Keep the data directory private. Set up the vault and acknowledge its recovery limitation. Create an encrypted backup before relying on the app.
2. **AI consent:** Projects begin private. Enable AI access on selected projects; uploaded files require separate consent. Only opted-in text content is retrieved. Keep credentials in the vault, not in notes or assistant messages.
3. **Live AI:** Supply `OPENAI_API_KEY` and `OPENAI_MODEL` as private server environment variables. Choose a model available in your API project. No model access or free API usage is assumed. The app uses the official OpenAI SDK and Responses API, with structured tool schemas and a five-turn tool limit. Calls use `store=False`.
4. **SMS:** Create a Twilio account, SMS-capable sender, and Verify service. Configure the environment variables in `.env.example`. Set `TGTOP_MODE=live`, an HTTPS origin, and the exact incoming webhook URL. Verify your phone again through the real provider; simulator verification cannot authorize live messaging.
5. **Other devices:** Host the service on an always-on machine with HTTPS, persistent storage, and one application process. Enroll each browser or Windows app by signing in. In Windows Setup, choose Connect to hosted service. On a phone, open the same HTTPS URL and use the browser’s Add to Home Screen / Install App option.
6. **Offline access:** In Connections, enable encrypted offline editing with a local passphrase. Unlock it after every app restart. Only projects, tasks, and notes are cached. Files and vault contents are not cached. Sync requires a valid online account session; conflicts show both versions.
7. **Notifications:** Enable desktop notifications in Settings. Windows uses native Electron notifications while the application is open. Browsers need notification permission and an active page. Missed reminders remain in delivery history when devices reconnect. This release does not implement background web push.

## Hosting

The local service is fully functional; it is not already deployed to the cloud. To receive SMS reminders while this PC is off, configure an always-on backend. Use `Dockerfile` and `deploy/compose.yaml` as deployment examples. Configure the Caddy hostname and private `.env`; set `TGTOP_HOST=0.0.0.0`, `TGTOP_DATA=/data`, and `TGTOP_ORIGIN=https://your-hostname`. The `.env` file is not automatically read by source mode; Docker Compose loads it, or set environment variables yourself in PowerShell/your hosting provider.

Before exposing a service, provision its account locally with `scripts/provision.py` against its persistent volume. Remote registration stays disabled unless the operator explicitly sets TGTOP_ALLOW_SIGNUP=1. Local registration supports additional users. Mount persistent `/data`, run one Uvicorn process, keep the service behind TLS, restrict host/container access, and back up the volume. Windows DPAPI keys are bound to the Windows user; move between hosts using an app-generated encrypted backup rather than copying that key file.

Example environment configuration without secrets:

```powershell
$env:TGTOP_DATA = 'D:\Private\TgTop'
$env:TGTOP_ORIGIN = 'https://tgtop.example.com'
$env:TGTOP_HOST = '0.0.0.0'
$env:TGTOP_MODE = 'live'
$env:TGTOP_APPROVED_ROOTS = 'D:\Projects;D:\School'
```

Set provider secrets separately through your hosting secret manager. Do not put them in this repository. Native external file references are service-local: a cloud service cannot dereference files on a powered-off PC. The current fixed backup agent backs up service data, not arbitrary remote PC folders.

## Codex integration

Codex’s supported MCP integration is separate from the OpenAI API assistant. Codex retains its own login/subscription and approval behavior; TgTop does not claim to embed or impersonate Codex.

Create a restricted token in Connections. Keep it in the private environment of the stdio MCP process as `TGTOP_MCP_TOKEN`; set `TGTOP_URL` to the common backend. Tokens expire after seven days and are revocable in device management. Configure Codex to run the Python interpreter from this project’s virtual environment, with `-m app.mcp_server` and the project directory as its working directory. If your Codex configuration does not support a working directory, use `PYTHONPATH` pointing to the source checkout. Never paste tokens into assistant prompts.

Example configuration, with no token included:

```toml
[mcp_servers.tgtop]
command = "C:\\path\\to\\TgTop\\.venv\\Scripts\\python.exe"
args = ["-m", "app.mcp_server"]
env_vars = ["TGTOP_MCP_TOKEN", "TGTOP_URL", "PYTHONPATH"]
```

TgTop rechecks project consent inside every tool, independently of model arguments. Vault, backups, device management, and SMS sending are not exposed through MCP. Only task creation and desktop reminder scheduling are permitted mutations. Instructions embedded in retrieved documents are untrusted data.

Official documentation consulted on October 11, 2026: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling), [Codex MCP integration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), and [Twilio webhook security](https://www.twilio.com/docs/usage/webhooks/webhooks-security).

## SMS commands

Supported grammar is deliberately bounded. Unsupported/ambiguous commands request clarification instead of guessing.

```text
Add task Prepare chemistry report
Remind me tomorrow at 6 PM to submit my assignment
What tasks are due this week?
Mark Prepare chemistry report complete
Summarize the tasks in my Website project
Start my approved backup workflow
HELP
```

Completion requires an exact unique task title. Project summaries and due-task results contain counts rather than private task/file contents. Backups enter `awaiting_approval` and need approval in a signed-in app, then explicitly run on the approved session. Secret requests are rejected. An authorized phone number alone cannot approve sensitive work.

Incoming webhooks use Twilio’s signature validator and the exact configured URL, then fetch the message from the provider to verify its creation time (five-minute window) and source/body. Durable message IDs prevent repeat execution. Outbound reminders send a generic private-workspace notice only. Provider submission is distinct from delivery; the scheduler polls the provider for terminal delivery status. A timeout or interrupted dispatch enters `needs_review`; after checking provider logs you can explicitly retry. Exactly-once delivery across a provider network failure is not claimed.

## Recovery and encryption

See [SECURITY.md](SECURITY.md). There are three independent passwords: account sign-in, vault master password, and a backup password for each snapshot. Offline copies optionally use a fourth, local-only passphrase. No master-password reset or recovery bypass exists.

Backups include database, the portable service key inside the encrypted archive, managed encrypted blobs, and vault ciphertext. A backup password alone restores ordinary records, but vault decryption still needs the original master password. External referenced files must be backed up independently. Restore replaces all records, revokes all sessions, and writes `before-restore.tgtop` protected by the entered backup password. JSON exports are plaintext and should be handled as private files.

## Build and verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm audit
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

The build uses a clean virtual environment, freezes the backend with PyInstaller, then packages Electron with an NSIS Windows installer. The installer is unsigned until you configure a code-signing certificate; Windows may show a publisher warning. Future macOS/Linux packages need platform-specific builds and testing.

See [delivery report](docs/DELIVERY.md) for verified workflows and remaining limitations. This is an early functional release, not a claim of an independently audited production security system.

ChatGPT plan sign-in and phone AI setup: see [CHATGPT.md](docs/CHATGPT.md).

## Shared cloud accounts

Connect before login using **Connect cloud account**, then use the same service address and username on every device. Connections now shows the active service and last sync check. HTTPS service validation preserves the current connection on failure. Your local workspace stays recoverable and separate. See [multi-device setup and migration](docs/CLOUD.md). Hosting is required; this package has not deployed a live cloud service.
# Automatic calendar texts

Each open task with a due date schedules one SMS one hour before its deadline by default. This includes approved school imports and existing tasks. Change this preference in Setup & settings. Automatic calendar texts bypass quiet hours to preserve the requested timing; manually scheduled reminders still respect quiet hours. New tasks with less than one hour remaining send on the next scheduler check. Overdue tasks expire without a late text. Completing, deleting, or removing a task's due date cancels its pending automatic reminder; moving the due date reschedules it. Recurring task occurrences receive separate reminders.

The always-on service needs a connected messaging provider and a live verified phone. Texts contain a generic private reminder notice. Failed or uncertain sends appear in delivery history and require review before retry. Hosting/provider interruptions can delay delivery; the app cannot guarantee exact arrival time.

