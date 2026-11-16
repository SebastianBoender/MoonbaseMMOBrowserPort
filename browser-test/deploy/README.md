# Deploy moonbasemmo.com on Ubuntu

Target: Ubuntu 24.04 LTS or newer with systemd, root/sudo access, and ports 80/443 available. The VPS runs Python's game host and a Caddy HTTPS reverse proxy. Game execution stays in each player's browser. Multiplayer still connects to **pigyak.com:1626**; this does not install a new SMUS backend.

## Deploy from this computer

1. Point the **A record for `moonbasemmo.com`** at the VPS IPv4 address. Only add an AAAA record if IPv6 reaches this VPS too.
2. Allow incoming TCP **80 and 443** in the VPS/provider firewall. Keep SSH access. Permit outgoing TCP **1626** to the existing game server and outgoing HTTP/HTTPS for packages/certificates. The script does not alter firewall rules.
3. From the project directory:

```bash
./browser-test/deploy/deploy.sh root@YOUR_VPS_IP
```

Replace `root` with a sudo-enabled SSH account if preferred. SSH keys/agent and ordinary `~/.ssh/config` settings work; no password or private key is stored by the script. The script packages the prepared assets, uploads them with SCP and runs the installer through SSH. No Windows EXE is uploaded or executed. A fresh Git clone needs your existing `MB_2010-10-08.exe` beside the root README so setup can recover the original movie; this private source asset is excluded from Git.

**This configuration replaces the existing HMC website frontend, as requested.** It backs up `/etc/caddy/Caddyfile`, installs a dedicated Moonbase configuration, and stops/disables Nginx and Apache if installed. It does not uninstall HMC data or blindly terminate custom applications/containers. If HMC owns ports 80/443 directly, the installer reports those listeners; stop that HMC service/container and rerun. An HMC backend on another port may remain running but is no longer routed by this frontend.

Caddy handles HTTPS issuance, renewal, HTTP-to-HTTPS redirects and WebSocket upgrades. DNS must resolve here and the challenge ports must be reachable before a certificate can be issued. Open **https://moonbasemmo.com** after deployment.

## Package/upload manually

```bash
./browser-test/deploy/deploy.sh --package-only
scp browser-test/deploy/dist/moonbase-deploy.tar.gz root@YOUR_VPS_IP:/tmp/
ssh root@YOUR_VPS_IP
mkdir -p /tmp/moonbase-release
tar -xzf /tmp/moonbase-deploy.tar.gz -C /tmp/moonbase-release
sudo bash /tmp/moonbase-release/install.sh
```

## Updates and service commands

Rerun the same deployment command for updates. Each installation creates a new release, switches `/opt/moonbase/current`, and restarts the service; existing player connections can disconnect during this update. Prior releases are retained.

```bash
sudo systemctl status moonbase caddy
sudo journalctl -u moonbase -u caddy -f
curl -f http://127.0.0.1:8765/api/status
sudo systemctl restart moonbase
```

The game host binds **127.0.0.1:8765 only**. Its systemd service runs as the unprivileged `moonbase` user with a read-only deployment directory. Production mode accepts the exact HTTPS browser origin, disables shared diagnostic downloads/collection and turns off per-packet multiplayer logging. Service logs go to the journal. Only `public/` is web-accessible.

To roll back, choose the prior release printed by the installer:

```bash
sudo ln -s /opt/moonbase/releases/PREVIOUS_RELEASE /opt/moonbase/rollback.next
sudo mv -Tf /opt/moonbase/rollback.next /opt/moonbase/current
sudo systemctl restart moonbase
```

To restore the former HMC frontend, restore its backed-up web configuration and re-enable the appropriate service. The installer prints the previous game release; Caddy backups are `/etc/caddy/Caddyfile.before-moonbase.*`. No game data is stored in the release directories.
