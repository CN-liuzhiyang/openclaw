---
name: server-deploy
description: >
  Deploy and manage OpenClaw personal AI assistant on Linux servers.
  Supports both source code deployment (with systemd or pm2) and Docker Compose deployment.
  Use this skill when the user mentions "deploy", "部署", "server", "服务器", "server-deploy",
  or wants to set up, update, check status, backup, or manage OpenClaw on a remote server.
  Also triggers for server maintenance tasks like SSL configuration, Nginx setup, health checks,
  rollback, or viewing logs. This skill assumes Claude Code is running directly ON the target
  server (not remotely via SSH).
version: "2.0.0"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Server Deploy — OpenClaw Deployment Skill

Deploy, manage, and maintain OpenClaw on Linux servers. This skill is designed to be used
by Claude Code running **directly on the server**, giving full local filesystem access.

Supports two deployment modes:
- **source** (default): Build from source code, managed by systemd or pm2. Best for developers who maintain their own fork.
- **docker**: Deploy via Docker Compose. Best for isolated, reproducible deployments.

## Usage

```
/server-deploy                        # Show available commands
/server-deploy check [--mode source|docker]  # Check server environment readiness
/server-deploy init [--mode source|docker] [--pm systemd|pm2]  # First-time deployment
/server-deploy update                  # Update to latest version
/server-deploy status                  # View all service statuses
/server-deploy backup                  # Backup OpenClaw data
/server-deploy rollback [--git-ref <tag|commit>]  # Rollback to previous version
/server-deploy nginx                   # Configure/update Nginx reverse proxy
/server-deploy ssl <domain>            # Configure Let's Encrypt SSL
/server-deploy logs                    # View service logs
```

## Prerequisites

This skill expects to run inside the OpenClaw project directory (the cloned repo/fork).

- **Source mode**: Node.js >= 22, pnpm, git
- **Docker mode**: Docker, Docker Compose, git

## Mode Detection

Commands automatically detect the current deployment mode:
1. systemd service `openclaw-gateway` exists → source mode
2. pm2 has `openclaw-gateway` process → source mode
3. Docker containers running → docker mode
4. Default: source mode

Override with `--mode source` or `--mode docker` on any command.

## Commands

### check — Environment Readiness Check

```bash
python3 .claude/skills/server-deploy/scripts/check_env.py [--mode source|docker]
```

**Source mode** checks: OS, Node.js 22+, pnpm, git, RAM, disk, ports, project files.
**Docker mode** checks: OS, Docker, Docker Compose, git, RAM, disk, ports, project files.

Present results to the user in a clear table format. If issues are found, offer to fix them.

### init — First-Time Deployment

The full deployment workflow. Execute these steps in order:

#### Step 1: Environment Check
Run `check_env.py` first. If critical issues are found, fix them before proceeding.

#### Step 2: Install Prerequisites

**Source mode:**
```bash
# Install Node.js 22 (if needed)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Install pnpm (if needed)
npm install -g pnpm
```

**Docker mode:**
```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker
```

#### Step 3: Security Hardening
```bash
apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

apt install -y fail2ban
systemctl enable fail2ban && systemctl start fail2ban
```

#### Step 4: Configure Environment
1. Copy `.env.example` to `.env` if it doesn't exist
2. Ask the user for required values:
   - AI provider API keys (at least one of: ANTHROPIC_API_KEY, OPENAI_API_KEY)
   - OPENCLAW_GATEWAY_TOKEN (auto-generate with `openssl rand -hex 32` if not set)
   - OPENCLAW_GATEWAY_BIND (default: "lan")
3. Set config and workspace directories:
   ```
   OPENCLAW_CONFIG_DIR=~/.openclaw
   OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace
   ```

#### Step 5: Deploy

**Source mode:**
```bash
python3 .claude/skills/server-deploy/scripts/deploy.py --mode source --pm systemd
# or: --pm pm2
```

This runs: `pnpm install` → `pnpm build` → install systemd service/pm2 config → start.

**Docker mode:**
```bash
python3 .claude/skills/server-deploy/scripts/deploy.py --mode docker
```

This runs: `docker compose build` → `docker compose up -d openclaw-gateway`.

#### Step 6: Health Check
```bash
python3 .claude/skills/server-deploy/scripts/health_check.py --mode source
```

#### Step 7: Nginx Setup (optional)
Ask the user if they want to set up Nginx reverse proxy. If yes, run the nginx setup.

#### Step 8: SSL Setup (optional)
If the user has a domain, offer to configure SSL with Let's Encrypt.

### update — Update to Latest Version

```bash
python3 .claude/skills/server-deploy/scripts/update.py [--mode source|docker]
```

**Source mode**: backup → `git pull` → `pnpm install` → `pnpm build` → restart service → health check.
**Docker mode**: backup → `git pull` → `docker compose build` → restart containers → health check.

If the health check fails, offers to rollback.

### status — Service Status

```bash
python3 .claude/skills/server-deploy/scripts/status.py [--mode source|docker]
```

**Source mode**: shows systemctl/pm2 status, PID, memory, uptime, gateway health, recent logs.
**Docker mode**: shows container status, resource usage, uptime, gateway health, recent logs.

### backup — Data Backup

```bash
python3 .claude/skills/server-deploy/scripts/backup.py
```

Backs up `~/.openclaw` (config, memory, sessions) to a timestamped archive in `~/openclaw-backups/`.

### rollback — Rollback to Previous Version

```bash
python3 .claude/skills/server-deploy/scripts/rollback.py [--mode source|docker] [--list]
```

**Source mode** supports two rollback methods:
- `--git-ref <tag|commit>`: Checkout a specific git tag/commit, rebuild, and restart.
- `--backup-file <path>`: Restore data from a backup archive.

**Docker mode**: Restores from backup archive, restarts containers.

Use `--list` to see available rollback targets (backups, git tags, recent commits).

### nginx — Nginx Reverse Proxy

```bash
python3 .claude/skills/server-deploy/scripts/setup_nginx.py
```

Installs Nginx (if needed), creates the reverse proxy configuration from template, enables the site, and tests.

### ssl — SSL Certificate

```bash
python3 .claude/skills/server-deploy/scripts/setup_ssl.py --domain <domain>
```

Installs certbot, obtains a Let's Encrypt certificate, and configures Nginx for HTTPS.

### logs — View Logs

**Source mode (systemd):**
```bash
journalctl -u openclaw-gateway -f --no-pager -n 100
```

**Source mode (pm2):**
```bash
pm2 logs openclaw-gateway --lines 100
```

**Docker mode:**
```bash
docker compose logs -f --tail 100 openclaw-gateway
```

## Channel Configuration

After deployment, the user may want to connect messaging channels:

**Source mode:**
```bash
node dist/index.js channels login          # WhatsApp (QR code)
node dist/index.js channels add --channel telegram --token <BOT_TOKEN>
node dist/index.js channels add --channel discord --token <BOT_TOKEN>
```

**Docker mode:**
```bash
docker compose run --rm openclaw-cli channels login
docker compose run --rm openclaw-cli channels add --channel telegram --token <BOT_TOKEN>
docker compose run --rm openclaw-cli channels add --channel discord --token <BOT_TOKEN>
```

Full channel docs: https://docs.openclaw.ai/channels

## Templates

| File | Purpose |
|------|---------|
| `templates/nginx-openclaw.conf` | Nginx reverse proxy config |
| `templates/env.template` | Environment variable reference |
| `templates/openclaw-gateway.service` | systemd service unit file |
| `templates/ecosystem.config.cjs` | pm2 ecosystem configuration |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/common.py` | Shared utilities (mode detection, service control) |
| `scripts/check_env.py` | Check server environment readiness |
| `scripts/deploy.py` | Execute deployment steps |
| `scripts/health_check.py` | Verify deployment health |
| `scripts/backup.py` | Backup OpenClaw data |
| `scripts/update.py` | Update to latest version |
| `scripts/rollback.py` | Rollback to previous version |
| `scripts/status.py` | Show service status |
| `scripts/setup_nginx.py` | Configure Nginx reverse proxy |
| `scripts/setup_ssl.py` | Configure Let's Encrypt SSL |

## Troubleshooting

### Common Issues

1. **Port 18789 already in use**: Another service is using the gateway port.
   ```bash
   lsof -i :18789
   # Kill the process or change OPENCLAW_GATEWAY_PORT in .env
   ```

2. **Source build fails (`pnpm build`)**: Ensure Node.js >= 22.12.0 and pnpm are installed.
   ```bash
   node --version   # Should be v22.x or higher
   pnpm --version   # Should be 10.x or higher
   ```

3. **systemd service fails to start**: Check logs and service file.
   ```bash
   journalctl -u openclaw-gateway -n 50 --no-pager
   systemctl cat openclaw-gateway
   ```

4. **pm2 process keeps restarting**: Check error logs.
   ```bash
   pm2 logs openclaw-gateway --err --lines 50
   ```

5. **Docker permission denied**: Current user not in docker group.
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

6. **Health check fails after deploy**: Service might need time to start.
   ```bash
   # Source mode
   journalctl -u openclaw-gateway -f
   # Docker mode
   docker compose logs openclaw-gateway
   # Wait 30s and retry health check
   ```

7. **Out of disk space**: Clean up old builds or Docker images.
   ```bash
   # Docker mode
   docker system prune -a
   # Source mode — remove old node_modules
   rm -rf node_modules && pnpm install
   ```
