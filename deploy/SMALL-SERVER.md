# TgTop on a 1 GB server

This profile targets Ubuntu x86-64 on Oracle's Always Free AMD micro instance. On October 12, 2026, Oracle successfully provisioned the 1 GB `tgtop-cloud` instance in Ashburn AD-2. SSH and encrypted swap were verified. Application deployment and account migration checks remain in progress. Actual application memory usage still requires verification on this host.

The app runs one Python process with at most eight concurrent connections/tasks; excess requests receive HTTP 503 and can be retried. The application and its Photon subprocess share a 600 MiB RAM cap, Caddy has 100 MiB, and the OS keeps the remaining RAM. Node's JavaScript heap has a 96 MiB cap. Container logs rotate at two 5 MiB files per service. These are limits, not measured usage guarantees. Keep Argon2 and AES-GCM settings unchanged.

Uploads have a 10 MB limit. Account backups have a 32 MB source limit and restores a 32 MB encrypted-file / 96 MB expanded-content limit. Larger workspaces need a larger host for application backup/restore; do not silently exclude files. Preserve independent backups before migration. Avoid concurrent large file operations on this small instance.

After installing Docker from its official Ubuntu repository, run:

```sh
sudo sh deploy/setup-small-host.sh
```

This installs cryptsetup and provisions 2 GiB of encrypted swap on the boot disk with a fresh random key at each boot. Swap may contain decrypted application data, so do not replace it with plaintext swap. This script does not configure any pre-existing swap; inspect `swapon --show` and resolve plaintext swap before processing private data. Swap prevents some memory spikes but does not replace RAM or guarantee sufficient capacity. Check that `tgtop-encrypted-swap.service` succeeds after reboot before launching the app.

Prefer building the x86-64 image on another Docker-equipped machine, then transfer the resulting image privately to the server. Never include live account data or `.env` in the source build:

```sh
docker build --platform linux/amd64 -t tgtop:small .
docker save -o tgtop-small.tar tgtop:small
```

On the server, load the transferred image, configure the root `.env` with the actual hostname and public signup disabled, then launch from the source root:

```sh
docker load -i tgtop-small.tar
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.small.yaml up -d --no-build
docker compose --env-file .env -f deploy/compose.yaml -f deploy/compose.small.yaml ps
docker stats --no-stream
```

The `--no-build` flag avoids dependency installation and image compilation on the tiny server. When no separate Docker-equipped builder exists, one initial build on the server may use its encrypted swap; watch memory and build failures. Provision the initial account privately using the existing provisioning script. Continue the HTTPS, restart, reminder, account migration, and two-device checks in ORACLE.md. Test Photon and AI while watching memory; if containers restart or requests fail under ordinary use, wait for a larger free instance rather than weakening encryption or creating a paid server.

References: [Compose memory and logging controls](https://docs.docker.com/reference/compose-file/services/), [Uvicorn concurrency limits](https://www.uvicorn.org/settings/).
