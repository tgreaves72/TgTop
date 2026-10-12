# TgTop on Oracle Always Free

Use the deployment steps below for a private, self-hosted installation. For a 1 GB server, include the limits and encrypted swap setup in [SMALL-SERVER.md](SMALL-SERVER.md). Keep deployment addresses, credentials, and account data outside the repository.

Use an Always Free-eligible Ubuntu instance in the account’s home region. Prefer Ampere A1 with 1 OCPU and 6 GB RAM, or 2 OCPUs and up to 12 GB RAM if the console confirms eligibility. Use a 50 GB boot volume at the free-eligible performance tier. Keep all boot/block storage within the account’s 200 GB free allowance. Existing account resources count toward those totals. Do not substitute a paid shape if free capacity is unavailable, and do not upgrade the account to Pay As You Go for this deployment.

Oracle may reclaim idle free servers and may have no available capacity. Preserve independent encrypted TgTop backups. Always Free does not provide an uptime SLA. Signup requires accurate account details and card verification, which the account owner completes privately.

## Deployment to perform after account access

1. Inspect current resources and free eligibility before creating anything. Create an isolated TgTop instance with a private SSH key. Keep the private key outside the source directory.
2. Configure network and host firewall rules: SSH only from the administrator’s approved address; HTTP/HTTPS for the application; no public access to port 8765. Use no separate paid load balancer or database.
3. Install Docker Engine and Compose on Ubuntu using the official Docker installation instructions. The source Dockerfile supports the base-image architecture selected on the instance; an ARM build still needs verification on the actual host.
4. Upload a clean source bundle only. Do not upload the PC’s live database, DPAPI key, private runtime settings, or provider credentials as source.
5. Configure an actual HTTPS hostname. No domain has been registered or selected; a free DNS hostname can be selected separately. Verify ownership and DNS resolution before running Caddy. Keep `.env` private and set the actual `TGTOP_DOMAIN`; leave public signup disabled.
6. Run the existing `deploy/compose.yaml` service with a persistent volume. Provision the first account privately using `scripts/provision.py`. Do not expose an unauthenticated first-account setup process.
7. Verify HTTPS, sign-in, task/file persistence after restart, service health, and two independent device sessions. Then use an encrypted account backup to migrate existing data, following `docs/CLOUD.md`. Re-authorize ChatGPT for the actual hostname. Recheck Photon before moving its live connection from the old service.
8. Enroll the home PC with the same HTTPS service and account, and test a task created on each device. Keep the untouched local account and recovery backup until all checks pass.

The current compose file has one application service, Caddy HTTPS, and persistent application/certificate volumes. It includes the Photon Node bridge. Paid AI or messaging usage remains separate from hosting costs.

Official references: [Oracle Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle signup FAQ](https://www.oracle.com/cloud/free/faq/), [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

