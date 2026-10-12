# TgTop on multiple devices

TgTop uses one always-on account service as the source of truth. Every device signs into the same HTTPS service with the same username and password. Different usernames keep separate workspaces. A standalone local installation does not automatically discover another computer or upload its data.

## What shares

Projects, tasks, project notes, uploaded managed files, deadlines, reminders, task history, settings, encrypted vault entries, and saved conversation records live on the service. An open app refreshes from that service every 15 seconds; Sync now refreshes immediately. The AI chat window itself shows the current session, while saved conversation records remain in the account. Conflicting offline task/note edits require explicit review. Pending edits use durable operation IDs so retries do not repeat actions. Device sessions can be revoked independently.

External file references and the directly linked Resume are paths on the service computer. They cannot open a file on a different, powered-off PC. Upload a managed copy to share that file; the existing direct Resume editor still requires the service computer’s file. Vault entries synchronize encrypted, and revealing them requires an explicit vault unlock. No offline file/vault cache exists.

## Hosting required

No cloud account or host has been provisioned. Obtain an always-on host that runs Docker Compose and persistent volumes, and a domain pointing to it. Hosting/domain fees depend on your provider. Photon provides messaging and ChatGPT provides AI; neither hosts the TgTop database.

On your host, place the TgTop source in a private directory and copy `.env.example` to `.env`. Set `TGTOP_DOMAIN` to your actual hostname without a protocol or path. Leave `TGTOP_ALLOW_SIGNUP=0`. Keep `.env` private. The deployment overrides host, port, public origin, and live mode automatically.

Run from the repository root:

```sh
docker compose --env-file .env -f deploy/compose.yaml up -d --build
docker compose --env-file .env -f deploy/compose.yaml exec tgtop python scripts/provision.py
```

The second command privately prompts for your initial cloud username/password. It refuses to overwrite an existing owner. DNS must point at the host, and inbound ports 80/443 must reach Caddy. Only the HTTPS reverse proxy is public; do not publish backend port 8765. Run exactly one backend replica because account keys, vault unlocks, scheduler locks, and SQLite live in one service process. Persistent Docker volumes hold the database, encrypted files, service keys, and HTTPS certificates.

This deployment includes Node and the official Photon SDK so configured Photon streams can run on the always-on host. Live provider credentials and verification remain private setup steps. Do not run two copies of the same messaging integration during migration: disconnect the old one before enabling it on the cloud host.

## Move the current local account safely

1. On the original PC, open Backup & restore and create an encrypted `.tgtop` backup with a private backup password. Keep an independent copy.
2. Deploy and provision the cloud service. In TgTop choose Connections & devices → Connect cloud account, or use that button on the login screen. Enter the HTTPS service address. TgTop checks the service before changing the saved address.
3. Sign into the receiving cloud account. Restore your backup there, typing RESTORE only after checking you selected the intended destination. Restore replaces that account’s data, keeps its username, and revokes its sessions. The restored password comes from the backup, so use the original local account password to sign in again. Your untouched local account remains on the original PC.
4. Reconnect ChatGPT on the cloud service so its OAuth callback belongs to the new hostname. Recheck Photon/provider status and phone verification. Re-link service-local file paths only where those files exist.
5. Install the Windows application on the home PC, choose Connect cloud account before login, and enter the same address. Sign into that same cloud username. A phone can open the same URL and install the web app using its browser’s install option.
6. Create a test task on one device, then Sync now on the other. Compare the task and device list. Revoke any unwanted sessions. Keep the original backup until migration and provider checks pass.

## Offline and recovery

Enable encrypted offline access separately on each device. Use a local passphrase to unlock cached tasks/notes after restart. Queued edits stay in that account’s encrypted local cache and upload once authenticated connectivity returns. The app displays stale/offline information and conflict counts. Resolve pending edits before switching services. Cloud connection settings survive app restarts. Use local workspace returns to that PC’s separate saved account; it does not copy or merge cloud data. When initial cloud loading fails, the desktop offers retry or returning to the local workspace.

Create encrypted account backups from the app and keep them away from the host. If you lose the host, restore a backup into a fresh receiving account. Losing the service encryption key without a valid encrypted backup makes stored data unrecoverable. Losing the vault master password prevents vault recovery even if ordinary account data can be restored.

## Encryption and limits

HTTPS encrypts network traffic. Records/files are encrypted on disk; the backend decrypts them for authenticated account requests and authorized AI processing. Windows protects the service key with DPAPI. Linux keeps the service key in a private permissions-restricted persistent volume; use encrypted host disks and protect volume backups. This is server-side encryption, not end-to-end encryption against the host administrator. Vault secrets remain encrypted under a separate user password until explicit unlock.

Verified here: automated independent-device sessions sharing tasks/files, conflict review/version updates, duplicate-operation handling, account separation and device revocation; desktop connection validation and packaging. Not verified here: deployment on a paid host, certificate issuance, physical second-PC connection, Docker image execution (Docker is unavailable in this environment), or live messaging after cloud migration.

## Selected hosting route

Oracle Always Free is now the selected route. Account signup and an eligible server are still pending. See [Oracle deployment steps](../deploy/ORACLE.md). The Railway configuration remains optional; no Railway deployment or subscription was created.
