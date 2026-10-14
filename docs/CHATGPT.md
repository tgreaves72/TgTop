# ChatGPT and Photon

TgTop uses the official Sign in with ChatGPT dynamic registration flow. It requests app-specific identity, refresh, and ChatGPT plan permissions. This does not authorize access to your ChatGPT conversation history or provide an OpenAI API key. Availability depends on the account, granted scopes, available models, and provider limits.

In Connections & devices, choose Manage ChatGPT, then Continue with ChatGPT. Complete sign-in and permission approval in your browser. Return to TgTop. The open connection panel updates automatically after authorization; choose an available model and save it. Existing TgTop account data stays in place. The ChatGPT connection adds an AI provider to that account; it does not replace your TgTop login password.

This local desktop flow uses an HTTP loopback callback at 127.0.0.1:8765/auth/callback. Authorization and token exchange use HTTPS with OpenAI. It is currently limited to the local Windows service. Hosted web sign-in needs a separately registered web client.

Registration uses PKCE S256, random state and nonce, a stable host ID, and the issued client ID. The service verifies ID-token signatures, issuer, audience, expiry, and nonce before accepting an account. Transactions expire after ten minutes, bind to an active TgTop session, and can complete once. Tokens and pending verifiers stay in encrypted service settings, outside browser storage, search, logs, and AI context. Refreshes serialize in the one-service architecture. Disconnect attempts remote refresh-token revocation and clears local tokens; failed remote revocation directs you to ChatGPT Settings.

The model picker loads the account's live model catalog. ChatGPT requests use the public Responses API with store=false and stream=true, and collect completed output items before requiring response.completed. Failed, incomplete, or interrupted streams do not count as success. There is no automatic fallback to separately billed API usage.

Provider gateway failures (HTTP 520–524) preserve the saved connection and show the actual gateway status. They do not trigger repeated sign-in or automatic replay of assistant actions. Retry later and review action history before resubmitting a request whose result is uncertain.

## Phone commands

From your verified phone, text the line assigned by Photon:

- AI add a task to School to finish my chemistry assignment.
- AI remind me tomorrow at 6 PM to submit my assignment in School.
- AI mark Finish chemistry assignment complete.
- AI how many tasks are open?
- AI summarize my Website project.
- AI start my backup.

Project names and completion titles must resolve uniquely. Creation defaults to Personal when no project is named. Enable AI access on target projects. Ambiguous commands ask for clarification. Backups wait for approval in your authenticated app.

Phone AI sends the incoming request to OpenAI to produce a structured intent. It sends no stored workspace or file content for that planning step. TgTop validates the intent and project permissions, performs the allowed action, and sends a fixed acknowledgment or count through Photon. It never forwards model prose, passwords, or file content to the phone. Incoming Photon checks still require verified sender, freshness, rate limit, and durable deduplication. Review activity before retrying an uncertain result.

Keep TgTop and this PC online. Reminders and commands do not run while the PC is off without an always-on backend. Photon transport availability and ChatGPT account usage limits remain provider-controlled.

Official contracts: https://developers.openai.com/siwc/token-sharing-open-source/sign-in, https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions, https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference.
