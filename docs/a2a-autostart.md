# A2A autostart on Linux (systemd user services)

> Language: English | [Tiếng Việt](a2a-autostart.vi.md)

This guide describes the existing COS host configuration and how to start the A2A bridge automatically after boot. No cron job or manually launched terminal is required for each login.

## 1. Components and scope

| Component | Startup mechanism | Role |
| --- | --- | --- |
| `cos-contextforge` | Docker Compose, `restart: unless-stopped` | MCP gateway, loopback port `4444` |
| `cos-control-broker` | Docker Compose, `restart: unless-stopped` | A2A broker, loopback port `4445` |
| `cos-mcp-tunnel.service` | systemd user service | Cloudflare Named Tunnel |
| `cos-multi-account-a2a.service` | systemd user service | Local OAuth MCP-to-A2A bridge, `127.0.0.1:8780` |

Enable `cos-multi-account-a2a.service` to start the local A2A bridge automatically. The unit currently uses:

- Script: `~/.config/mcp-a2a-bridge/run_bridge.py`
- Config: `~/.config/mcp-a2a-bridge/bridge.yaml`
- Environment: `~/.config/mcp-a2a-bridge/bridge.env`
- Python: `~/.local/share/pipx/venvs/mcp-a2a-bridge/bin/python`
- OAuth state: `~/.local/state/cos-multi-account-a2a/oauth.json`
- Listen address: `127.0.0.1:8780` (loopback only)

Do not add `bridge.env`, OAuth state, tokens, Cloudflare tokens, or `.env` to Git or shared documentation.

## 2. Requirements before enabling autostart

1. Enable Docker Engine at system startup if ContextForge and the broker must start after reboot:

   ```bash
   sudo systemctl enable --now docker
   systemctl is-enabled docker
   systemctl is-active docker
   ```

2. Complete the first OAuth login in an active desktop session. The unit runs as user `long`; on first run, if no OAuth state exists, the bridge opens a browser for Auth0 login. Run:

   ```bash
   systemctl --user start cos-multi-account-a2a.service
   journalctl --user -u cos-multi-account-a2a.service -f
   ```

   Complete OAuth in the browser. After a successful callback, the log must contain `OAuth MCP session initialized` and the service must be `active`. Check that the state file exists without printing token contents:

   ```bash
   test -s ~/.local/state/cos-multi-account-a2a/oauth.json && echo 'OAuth state exists'
   stat -c '%a %U:%G %n' ~/.local/state/cos-multi-account-a2a/oauth.json
   ```

   The OAuth state file must be readable/writable only by the current user (mode `600`). Do not copy this file to another user or machine.

3. If the first login fails, inspect the journal, fix the cause, and retry. Do not enable a restart loop before OAuth completes.

## 3. Enable startup after reboot

After OAuth is complete and the service is stable:

```bash
systemctl --user enable cos-multi-account-a2a.service
systemctl --user enable cos-mcp-tunnel.service
systemctl --user enable cos-loop-watchdog.service
```

The user manager is currently configured with `Linger=yes`. This allows the systemd user manager and units under `WantedBy=default.target` to run after boot, even before the user signs in to the GUI. Verify:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user is-enabled cos-multi-account-a2a.service
systemctl --user is-enabled cos-mcp-tunnel.service
systemctl --user is-enabled cos-loop-watchdog.service
```

If `Linger=no`, enable it for the current user:

```bash
sudo loginctl enable-linger "$USER"
```

Linger does not create an OAuth token and does not replace the initial Auth0 login. Complete OAuth while the desktop is active before relying on autostart.

## 4. Check service state and A2A endpoint

```bash
systemctl --user status cos-multi-account-a2a.service --no-pager
journalctl --user -u cos-multi-account-a2a.service -b --no-pager -n 100
curl -fsS http://127.0.0.1:8780/health

docker compose ps
curl -fsS http://127.0.0.1:4444/health
curl -fsS http://127.0.0.1:4445/healthz
```

Expected:

- `cos-multi-account-a2a.service`: `active (running)`;
- local A2A health endpoint: HTTP 200;
- `cos-contextforge`: running/healthy;
- `cos-control-broker`: running/healthy.

A health check confirms only that the process/HTTP endpoint is alive. It does not prove peer ACL, inbox delivery, worker wake-up, or a live A2A round-trip. Send a message -> read the recipient inbox -> reply -> read the sender inbox to verify Workstream-to-Workstream communication.

## 5. Control the service

```bash
# Enable now and at boot
systemctl --user enable --now cos-multi-account-a2a.service

# Temporarily stop (keeps autostart configuration)
systemctl --user stop cos-multi-account-a2a.service

# Start again
systemctl --user start cos-multi-account-a2a.service

# Disable autostart
systemctl --user disable cos-multi-account-a2a.service

# Follow logs in real time
journalctl --user -u cos-multi-account-a2a.service -f
```

Do not use `docker compose down -v` to restart the gateway/broker; that may delete persistent data. For containers, use `docker compose up -d` or `docker compose restart <service>` from the correct deployment directory.

## 6. OAuth limitations

The bridge currently uses OAuth Authorization Code + PKCE, stores the access token in a user-only file, does not request `offline_access`, and does not use the refresh-token grant. When the access token expires, the bridge needs a new Auth0 browser sign-in. Therefore:

- `Restart=on-failure` restarts the process after failure; it does not renew tokens;
- if the bridge restarts after reboot while the token is still valid, it may initialize the MCP session without interaction;
- if the token has expired, sign in again in an interactive desktop session, then start the service again;
- do not enable `offline_access` or store refresh tokens without a design for rotation, revocation, and recovery.

## 7. Disable autostart

```bash
systemctl --user disable --now cos-multi-account-a2a.service
```

This command only disables/stops the local bridge; it does not delete OAuth state, broker database, ContextForge database, or Cloudflare configuration.

## 8. Current configuration checked

On the host inspected while this document was written:

- `cos-mcp-tunnel.service`: enabled;
- `cos-loop-watchdog.service`: enabled;
- `cos-multi-account-a2a.service`: exists but is disabled and inactive;
- user lingering: enabled (`Linger=yes`);
- Docker Compose sets `restart: unless-stopped` for `contextforge` and `cos-control-broker`.

Therefore, adding this guide does not mean the A2A bridge autostart is enabled. Mark it complete only after enabling the service, checking its state, and running a reboot acceptance test.
