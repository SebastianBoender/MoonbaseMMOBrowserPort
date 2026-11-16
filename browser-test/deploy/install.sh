#!/usr/bin/env bash
# Run on Ubuntu from an unpacked deployment archive. Does not run original binaries.
set -Eeuo pipefail
umask 022
[[ $EUID == 0 ]] || { echo 'Run this installer with sudo.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DOMAIN=$(cat "$SOURCE/domain.txt")
[[ "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$ ]] || { echo 'Invalid domain.txt.' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu ]] || { echo 'This installer targets Ubuntu 24.04 or newer.' >&2; exit 1; }
dpkg --compare-versions "$VERSION_ID" ge 24.04 || { echo 'Ubuntu 24.04+ required.' >&2; exit 1; }
[[ -f "$SOURCE/public/game/moonbase-browser.dir" && -f "$SOURCE/public/vendor/dirplayer-0.8.1/dirplayer-diagnostic.js" ]] || { echo 'Incomplete deployment package.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 caddy curl ca-certificates
getent passwd moonbase >/dev/null || useradd --system --user-group --home-dir /var/lib/moonbase --shell /usr/sbin/nologin moonbase
install -d -m 0755 /opt/moonbase/releases /etc/caddy/moonbase.d
RELEASE="/opt/moonbase/releases/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -m 0755 "$RELEASE"
cp -a "$SOURCE/public" "$RELEASE/public"
install -m 0644 "$SOURCE/serve.py" "$SOURCE/mus_bridge.py" "$RELEASE/"
chown -R root:root "$RELEASE"
find "$RELEASE" -type d -exec chmod 0755 {} +
find "$RELEASE" -type f -exec chmod 0644 {} +
python3 -m py_compile "$RELEASE/serve.py" "$RELEASE/mus_bridge.py"
# A symlink switch preserves the previous release for a simple rollback.
PREVIOUS=$(readlink -f /opt/moonbase/current || true)
ln -s "$RELEASE" /opt/moonbase/current.next
mv -Tf /opt/moonbase/current.next /opt/moonbase/current
cat > /etc/systemd/system/moonbase.service <<UNIT
[Unit]
Description=Moonbase browser host and fixed SMUS bridge
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=moonbase
Group=moonbase
WorkingDirectory=/opt/moonbase/current
ExecStart=/usr/bin/python3 -u /opt/moonbase/current/serve.py --port 8765 --public-origin https://$DOMAIN --production
Restart=on-failure
RestartSec=3
TimeoutStopSec=10
Environment=PYTHONDONTWRITEBYTECODE=1
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077
TasksMax=512
LimitNOFILE=4096
MemoryMax=512M
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
# This VPS's previous HMC frontend may be replaced. Keep the old Caddyfile
# as a timestamped backup, then use a dedicated config for Moonbase.
if [[ -f /etc/caddy/Caddyfile ]]; then
  cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-moonbase.$(date -u +%Y%m%dT%H%M%SZ)"
fi
printf '%s\n' 'import /etc/caddy/moonbase.d/moonbase.caddy' > /etc/caddy/Caddyfile
cat > /etc/caddy/moonbase.d/moonbase.caddy <<CADDY
# Managed by Moonbase deploy/install.sh
$DOMAIN {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8765
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# HMC's old Nginx/Apache frontend is intentionally retired on this VPS.
for unit in nginx apache2; do
  if systemctl cat "$unit.service" >/dev/null 2>&1; then
    systemctl disable --now "$unit.service"
  fi
done
systemctl daemon-reload
systemctl enable moonbase caddy
systemctl restart moonbase
READY=0
for attempt in {1..20}; do
  if curl --fail --silent http://127.0.0.1:8765/api/status >/dev/null; then READY=1; break; fi
  sleep 1
done
if [[ "$READY" != 1 ]]; then
  echo 'Backend failed readiness check. Inspect: journalctl -u moonbase -n 50' >&2
  echo "Previous release: $PREVIOUS" >&2
  exit 1
fi
if ! systemctl is-active --quiet caddy; then
  # A custom HMC process or container may still hold these ports. Report the
  # owners instead of guessing which unrelated service is safe to stop.
  if ss -ltnp '( sport = :80 or sport = :443 )' | tail -n +2 | grep -q .; then
    ss -ltnp '( sport = :80 or sport = :443 )' >&2
    echo 'Stop the listed HMC listener/container, then rerun install.sh.' >&2
    exit 1
  fi
  systemctl start caddy
else
  systemctl reload caddy
fi
printf '\nInstalled https://%s\nCurrent release: %s\nPrevious release: %s\n' "$DOMAIN" "$RELEASE" "${PREVIOUS:-none}"
echo 'Caddy obtains/renews HTTPS automatically once DNS points here and TCP 80/443 are reachable.'
echo 'The backend listens only on 127.0.0.1:8765; multiplayer still uses pigyak.com:1626.'
echo 'Firewall rules were not changed. Allow inbound TCP 80/443 and outbound TCP 1626.'
echo 'Logs: journalctl -u moonbase -u caddy -f'
