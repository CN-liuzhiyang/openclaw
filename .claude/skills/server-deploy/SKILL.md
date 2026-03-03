---
name: server-deploy
description: >
  Deploy and manage OpenClaw personal AI assistant on Linux servers using Docker Compose.
  Use this skill when the user mentions "deploy", "部署", "server", "服务器", "server-deploy",
  or wants to set up, update, check status, backup, or manage OpenClaw on a remote server.
  Also triggers for server maintenance tasks like SSL configuration, Nginx setup, health checks,
  rollback, or viewing logs. This skill assumes Claude Code is running directly ON the target
  server (not remotely via SSH).
version: "1.0.0"
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

## Usage

```
/server-deploy              # Show available commands
/server-deploy check        # Check server environment readiness
/server-deploy init         # First-time deployment (full setup)
/server-deploy update       # Update to latest version
/server-deploy status       # View all service statuses
/server-deploy backup       # Backup OpenClaw data
/server-deploy rollback     # Rollback to previous version
/server-deploy nginx        # Configure/update Nginx reverse proxy
/server-deploy ssl <domain> # Configure Let's Encrypt SSL
/server-deploy logs         # View service logs
```

## Prerequisites

This skill expects to run inside the OpenClaw project directory (the cloned fork).
The project should contain `docker-compose.yml` and `docker-setup.sh` from upstream.

## Commands

### check — Environment Readiness Check

Run the environment checker to verify the server meets all requirements:

```bash
python3 .claude/skills/server-deploy/scripts/check_env.py
```

This checks: OS, Docker, Docker Compose, available RAM, disk space, required ports (18789, 18790, 80, 443), and existing installations. Present results to the user in a clear table format.

If issues are found, offer to fix them automatically (install Docker, open ports, etc.).

### init — First-Time Deployment

The full deployment workflow. Execute these steps in order:

#### Step 1: Environment Check
Run `check_env.py` first. If critical issues are found, fix them before proceeding.

#### Step 2: Install Docker (if needed)
```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker
```

#### Step 3: Security Hardening
```bash
# Firewall
apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# fail2ban
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

#### Step 5: Deploy with docker-setup.sh
The official setup script handles image building, onboarding, and gateway startup:
```bash
chmod +x docker-setup.sh
./docker-setup.sh
```

If docker-setup.sh has issues (e.g., interactive prompts that block), fall back to manual deployment:
```bash
docker compose build
docker compose up -d openclaw-gateway
```

#### Step 6: Health Check
```bash
python3 .claude/skills/server-deploy/scripts/health_check.py
```

#### Step 7: Nginx Setup (optional)
Ask the user if they want to set up Nginx reverse proxy. If yes, run the nginx setup.

#### Step 8: SSL Setup (optional)
If the user has a domain, offer to configure SSL with Let's Encrypt.

### update — Update to Latest Version

```bash
python3 .claude/skills/server-deploy/scripts/update.py
```

This script:
1. Creates a backup before updating
2. Pulls the latest changes from upstream
3. Rebuilds the Docker image
4. Restarts services
5. Runs health check

If the health check fails, offers to rollback.

### status — Service Status

```bash
python3 .claude/skills/server-deploy/scripts/status.py
```

Shows: container status, uptime, resource usage, port bindings, health check results, and recent logs.

### backup — Data Backup

```bash
python3 .claude/skills/server-deploy/scripts/backup.py
```

Backs up `~/.openclaw` (config, memory, sessions) to a timestamped archive in `~/openclaw-backups/`.

### rollback — Rollback to Previous Version

```bash
python3 .claude/skills/server-deploy/scripts/rollback.py
```

Lists available backups and restores from the selected one. Also reverts Docker image if a previous image tag exists.

### nginx — Nginx Reverse Proxy

```bash
python3 .claude/skills/server-deploy/scripts/setup_nginx.py
```

Installs Nginx (if needed), creates the reverse proxy configuration from template, enables the site, and tests the configuration.

The Nginx config template is at:
```
.claude/skills/server-deploy/templates/nginx-openclaw.conf
```

### ssl — SSL Certificate

```bash
python3 .claude/skills/server-deploy/scripts/setup_ssl.py --domain <domain>
```

Installs certbot, obtains a Let's Encrypt certificate, and configures Nginx for HTTPS. Requires a domain name that resolves to this server.

### logs — View Logs

```bash
docker compose logs -f --tail 100 openclaw-gateway
```

## Channel Configuration

After deployment, the user may want to connect messaging channels. Guide them through:

```bash
# WhatsApp (QR code scan)
docker compose run --rm openclaw-cli channels login

# Telegram
docker compose run --rm openclaw-cli channels add --channel telegram --token <BOT_TOKEN>

# Discord
docker compose run --rm openclaw-cli channels add --channel discord --token <BOT_TOKEN>
```

Full channel docs: https://docs.openclaw.ai/channels

## Templates

| File | Purpose |
|------|---------|
| `templates/nginx-openclaw.conf` | Nginx reverse proxy config |
| `templates/env.template` | Environment variable reference |

## Scripts

| Script | Purpose |
|--------|---------|
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

2. **Docker permission denied**: Current user not in docker group.
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

3. **Health check fails after deploy**: Container might need time to start.
   ```bash
   docker compose logs openclaw-gateway
   # Wait 30s and retry health check
   ```

4. **Out of disk space**: Docker images can be large.
   ```bash
   docker system prune -a  # Remove unused images
   ```
