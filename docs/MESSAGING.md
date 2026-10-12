# Connecting real messaging

Open Connections & devices → Connect Photon or Twilio. Credentials are saved in encrypted service configuration, never source code, search, AI tools, or activity logs. These service credentials are available to the reminder scheduler while the personal credential vault is locked. On Windows the service encryption key is protected by the current user's Windows DPAPI account.

## Photon

### Spectrum (current dashboard, Stable SDK)

Choose **Photon Spectrum** in TgTop. Copy the project ID and project secret from the Photon project's Settings into the masked private setup form. TgTop encrypts the secret in service configuration and passes it directly to the official `@spectrum-ts/core` and `@spectrum-ts/imessage` SDKs through private process pipes. No credential appears in process arguments, AI context, exports, or logs. SDK telemetry is disabled.

Save and check the connection, then configure and verify your phone using the real code delivered through the assigned Photon line. Registered project users can send commands while the service is running. Incoming messages arrive over the authenticated SDK stream, so this mode does not need a public webhook. TgTop accepts only direct, inbound text from its verified phone, rejects old messages, applies rate limits, and stores message IDs durably before execution. Sensitive operations require approval inside TgTop.

Photon chooses its managed messaging transport. A connection check or an iMessage reply does not prove carrier SMS delivery. Test the actual transport and delivery receipt before relying on reminders. Free shared lines restrict recipients to registered project users; plan/transport availability belongs to Photon.

The SDK reconnects its stream, and TgTop restarts a failed bridge with the scheduler. Five-minute freshness limits intentionally reject stale commands after downtime. For reminders while this PC is off, run the backend and packaged Node bridge on an always-on host. The Node runtime is included in the Windows package. For source execution install Node.js and run `npm ci`.

Official Stable documentation: https://photon.codes/docs/spectrum-ts/getting-started and https://photon.codes/docs/spectrum-ts/providers/imessage.

### Advanced API (legacy)

This implementation uses Photon's official **Advanced iMessage HTTP Proxy** and **Photon Webhook bridge**. It does not accept Spectrum project IDs/project secrets. Ask Photon for a hosted Advanced iMessage server with SMS access, a server HTTPS URL under photon.codes, and its API key. Register your recipient phone in the Photon project where required. Messaging availability, supported channels, number provisioning, and charges depend on the assigned Photon account.

1. Create/configure the Photon account and obtain the hosted server URL and API key.
2. Deploy/configure the official Photon Webhook bridge following its documentation. This bridge needs its own PostgreSQL/Bun services. TgTop does not provision those services automatically.
3. Register your hosted TgTop endpoint `https://YOUR_HOST/api/sms/photon/incoming` in the bridge. Copy the bridge's signing secret into TgTop's private setup form.
4. Save and check the connection. This checks provider credentials; it does not claim that incoming delivery is already working.
5. Choose Configure & verify. TgTop sends a real SMS code through Photon. Enter that code in your authenticated TgTop session. The code is never displayed by the app or included in logs.
6. Send `add task Test incoming command` from the verified phone. Check the task in the calendar's Without a date section. Send `tasks due this week` for a private count.
7. Create a short SMS reminder and inspect delivery history. TgTop records submission separately from provider-confirmed delivery. Network failures after a submission may need manual review before retrying; blind retries could send duplicate messages.

Outbound requests go only to `https://imessage-swagger.photon.codes`, with the server URL/API key encoded as the proxy's documented bearer credential. That encoding is not encryption; HTTPS protects transport. SMS sends explicitly select `service: SMS`. Provider errors are replaced with generic messages.

Incoming bridge requests use HMAC-SHA256 over the timestamp and raw body. TgTop checks signature, five-minute timestamp freshness, verified sender, provider message content/sender/date, rate limits, and durable message IDs before running a command. Repeated IDs cannot execute again. A failed reply after an executed command is logged for review rather than executing the command again. Backups and other sensitive operations still require approval in an authenticated application session.

Official contracts checked October 11, 2026:

- https://github.com/photon-hq/advanced-imessage-http-proxy
- https://github.com/photon-hq/webhook
- https://photon.codes/docs/spectrum-ts/getting-started (implemented by the Spectrum adapter above)

## Twilio alternative

Provide an SMS-capable sending number, account SID, auth token, Verify service SID, and public HTTPS webhook URL `https://YOUR_HOST/api/sms/incoming`. Configure the sending number's incoming webhook in Twilio. TgTop checks Twilio signatures against the exact configured public URL and fetches incoming message details to reject stale/replayed commands. Verify the recipient through Twilio Verify before sending reminders.

## PC off and development

The Windows local service requires this PC to remain awake. Reminders while it is off require an always-on HTTPS backend with the same private provider setup and account data. A localhost address cannot receive public provider webhooks. Account/provider provisioning, public hosting, and a real send/receive test remain required before calling this connection live.

The development command simulator is under a separate expandable section and never sends a real message. No provider account or credentials are included in the installer. Provider mock tests verify request shapes and authorization behavior, not carrier delivery.
