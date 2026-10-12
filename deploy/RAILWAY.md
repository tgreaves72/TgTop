# Railway deployment status

Prepared locally. Not deployed: Railway is not yet connected to this chat and no hosting account/project has been selected. No private application records or credentials have been uploaded.

## Intended deployment

One TgTop Docker service, one persistent volume mounted at `/data`, public HTTPS on the generated Railway domain, backend target port 8765, and server sleeping disabled. A custom domain is optional. `railway.json` sets Docker build, one replica, health checks, and failure restarts. The volume must be created separately; the configuration file does not create it.

Set these service variables:

```text
TGTOP_HOST=0.0.0.0
TGTOP_PORT=8765
TGTOP_DATA=/data
TGTOP_MODE=live
TGTOP_ALLOW_SIGNUP=0
RAILWAY_RUN_UID=0
```

After generating the Railway domain, set `TGTOP_ORIGIN` to its exact HTTPS origin and deploy/redeploy. Do not use a guessed hostname. The container entrypoint initializes ownership of `/data`, then drops to the `tgtop` user before starting the server. This handles Railway’s root-owned volumes without running the application as root. Existing volume contents must already belong to that user; the entrypoint deliberately does not recursively rewrite ownership.

Do not expose signup during initial deployment. Provision the first account in the service terminal with `python scripts/provision.py`, entering passwords privately. Then migrate the original account using the encrypted backup/restore flow in `docs/CLOUD.md`. Keep the local installation and its recovery copy intact. Re-authorize ChatGPT for the cloud hostname and test messaging before switching the original device.

## Required verification before device connection

Check `/api/status` over HTTPS, authenticated sign-in, uploaded file access, a saved task across a service restart, two independent device sessions, stale-edit conflict resolution, and volume backup/restore. Check provider integration status without exposing credentials. Enable Railway volume backups and keep an independent encrypted application backup.

Official references: [persistent volumes](https://docs.railway.com/volumes/reference), [public networking](https://docs.railway.com/networking/public-networking), [deployment configuration](https://docs.railway.com/config-as-code/reference), [pricing](https://docs.railway.com/pricing).

Hobby currently starts at $5/month including that amount of usage; additional resource use adds charges. The provider determines the final bill. No purchase or billable deployment has occurred here. Docker execution remains untested locally because Docker is not installed.
