#!/bin/sh
# Run once on the Ubuntu server as root, after Docker installation.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
apt-get update
apt-get install -y cryptsetup
install -d -m 700 /var/lib/tgtop-swap
swapfile=/var/lib/tgtop-swap/encrypted.swap
if [ -e "$swapfile" ]; then
  [ -f "$swapfile" ] && [ ! -L "$swapfile" ] && [ "$(stat -c %s "$swapfile")" = 2147483648 ] || {
    echo 'Unexpected existing swap file. Review it manually.' >&2; exit 1;
  }
else
  umask 077
  dd if=/dev/zero of="$swapfile" bs=1M count=2048 status=progress
fi
chmod 600 "$swapfile"
cat > /etc/systemd/system/tgtop-encrypted-swap.service <<'UNIT'
[Unit]
Description=TgTop encrypted temporary swap
After=local-fs.target
Before=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/cryptsetup open --type plain --cipher aes-xts-plain64 --key-size 256 --key-file /dev/urandom /var/lib/tgtop-swap/encrypted.swap tgtop-swap
ExecStart=/usr/sbin/mkswap /dev/mapper/tgtop-swap
ExecStart=/usr/sbin/swapon /dev/mapper/tgtop-swap
ExecStop=/usr/sbin/swapoff /dev/mapper/tgtop-swap
ExecStop=/usr/sbin/cryptsetup close tgtop-swap

[Install]
WantedBy=multi-user.target
UNIT
install -d -m 755 /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/tgtop-swap.conf <<'UNIT'
[Unit]
Requires=tgtop-encrypted-swap.service
After=tgtop-encrypted-swap.service
UNIT
printf 'vm.swappiness=10\n' > /etc/sysctl.d/90-tgtop-small.conf
sysctl -p /etc/sysctl.d/90-tgtop-small.conf
systemctl daemon-reload
systemctl enable --now tgtop-encrypted-swap.service
swapon --show
free -m
