# Security and recovery model

## Boundaries

TgTop supports separate username-based accounts. Each account has its own encrypted database, managed files, private settings, vault, sessions, events, and integrations. Request-local account selection applies to authenticated APIs, OAuth callbacks, background reminder processing, and incoming phone commands. AI access stays separately restricted per project and file. Team roles and shared projects are not implemented. Revocation invalidates server access and locks that session’s vault key. Revocation cannot erase copies a previously authorized device already downloaded; remove its offline storage on that device too.

The browser and Electron renderer receive no server key. Authentication cookies are HttpOnly, SameSite=Strict, and Secure on HTTPS. Mutating cookie requests check the exact configured Origin and an application header. Bearer tokens are hashed at rest; AI-scoped tokens are restricted to three consent-checked tools. Device enrollment is a new named account session, not hardware attestation. Sessions expire after seven days. Login and vault attempts are rate-limited in the application process; run one service process. There is no passkey, MFA, or email password recovery in this release.

## Stored data

Normal record JSON, private settings, uploaded files, and event-independent payloads use AES-256-GCM with random nonces. The service decrypts this data for authorized UI/API requests. The normal data key is protected with Windows DPAPI under the service’s Windows user. Unix deployments use a mode-0600 key in a mode-0700 private data directory; protect the volume and hosting identity. Encryption does not protect against an attacker who controls the service process, its host user, or unlocked memory. Record types, stable IDs, event metadata, file sizes, and relationships can reveal metadata to someone who can read the database. No plaintext content search index is built; authorized content is decrypted in memory for search.

Vault keys use Argon2id (64 MiB memory, three iterations, two lanes), a random salt, and AES-256-GCM. Ciphertexts authenticate the credential ID. Vault keys are held only in service memory for a specific session, with a hard five-minute expiry checked before every use. Lock overwrites the mutable cached key buffer, but Python/runtime copies are not guaranteed to be zeroized. Values are masked in UI; reveals close after twenty seconds; visibility changes lock an open vault view. Explicit unlock is always required after service restart.

There is **no recovery key and no master-password reset that decrypts the vault**. Account password and vault master password are independent. Keep the master password separately and make encrypted backups. If the master password is forgotten, vault secrets are unrecoverable even with a database backup and server key.

Backups encrypt the current account’s portable snapshot using Argon2id and AES-256-GCM with fresh salt and nonce. The included portable server key is inside that encrypted archive. Backup passwords are not stored. Losing a backup password makes that snapshot unrecoverable. Restore checks integrity before replacing data and preserves a pre-restore encrypted snapshot. Exported JSON and downloaded originals are outside application encryption.

Encrypted offline task/note copies use browser Web Crypto AES-GCM and a PBKDF2-SHA256 key (600,000 iterations) derived from an opt-in local passphrase and random salt. Only ciphertext, IV, and salt persist in IndexedDB, namespaced by service origin and username. Sign-out clears in-memory data and queued changes; encrypted changes remain in their account’s cache. No vault values or managed file contents are cached. An unlocked renderer necessarily has access to decrypted cached tasks/notes. Close or sign out to drop its in-memory local key. Device revocation prevents server access but cannot revoke offline decryption keys remotely.

## AI and integrations

Project and file permissions default to false. Text from approved sources may be decrypted on the service and sent to OpenAI through HTTPS for enabled API calls. It is not end-to-end encrypted against that authorized provider. OpenAI requests use `store=False`; provider retention policies still apply. Only bounded text-file retrieval is implemented; PDFs, scanned documents, and binary formats are not extracted for AI.

Credentials are excluded from assistant schemas, source retrieval, app state ciphertext fields, exports, SMS, and notification bodies. MCP tokens cannot reach vault or backup endpoints. A fixed secure credential-service operation can check a vault API key against OpenAI’s `/v1/models` after explicit vault unlock and app approval; no caller-controlled URL is allowed and only a status returns. No automatic vault-backed AI credential grant exists; each account can authorize its own encrypted ChatGPT connection. Environment-based API credentials belong only to the original device owner.

Document instructions are data. Retrieval/tool descriptions and assistant instructions reinforce that boundary; server permission checks are authoritative. The limited tool surface prevents arbitrary shell execution, uploads to outside destinations, secret revelation, or destructive actions through AI. No prompt-injection defense is assumed perfect.

## Remote commands and reminders

Twilio signatures use the official validator; provider message lookup checks freshness and source before execution. Only a live-verified stored phone can use live commands. Durable IDs prevent repeat execution; rate limits are per process. SIM swapping, a compromised carrier, or an already compromised phone remains a risk for low-risk task commands. Sensitive actions must be approved in an authenticated app and cannot be authorized by SMS alone.

Outgoing SMS/desktop notifications use generic notices, never vault values or file contents. Reminder dispatch is recorded before provider calls. Ambiguous network failures require review before retry; provider delivery is not assumed from successful submission. A process restart recovers interrupted dispatch to `needs_review`. Desktop reminders remain `waiting_device` until a device acknowledges delivery.

The restricted workflow surface permits only an encrypted backup of service data. No arbitrary shell, scripting, destination path, or file deletion is accepted. Approved folder references are resolved and checked every read, including symlink resolution. A 30-second timeout discards the response; a Python worker already producing a backup may finish its bounded internal computation after cancellation. There is no standalone remote PC agent or full process sandbox in this release.

## Operational limitations

Use an always-on TLS backend for live SMS and common device sync. Keep one service process, persistent storage, private host permissions, backups, and provider secrets outside source control. Multi-process scheduling, automatic disaster failover, public multi-user hosting, MFA, background web push, and a comprehensive security audit remain future work. The Windows package is unsigned unless a signing certificate is supplied.

The encrypted account directory stores usernames and stable workspace IDs separately from account backups. Password hashes use Argon2id in each account database. Restoring a workspace retains the receiving account’s username and revokes its restored sessions. Device owners retain OS-level access to the service and its storage; application account separation does not defend against compromise of that operating-system account. Remote registration is disabled unless an operator explicitly enables it.

Cloud devices use one HTTPS account service. Service switching checks the new address before saving it and never transfers local records implicitly. Connection probes omit cookies and reject redirects. Browser caches remain separated by service origin and username. Linux cloud storage uses private filesystem permissions for service keys; protect persistent volumes with host disk encryption and independent encrypted backups. This release does not implement encryption that hides ordinary account data from the hosting administrator. See docs/CLOUD.md for migration and device-local file limitations.
