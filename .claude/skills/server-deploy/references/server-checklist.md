# Server Preparation Checklist

Pre-deployment checklist for setting up a Linux server for OpenClaw.

## Before You Start

- [ ] Server running Ubuntu 22.04+ or Debian 12+
- [ ] Root or sudo access
- [ ] At least 2 GB RAM (4 GB recommended)
- [ ] At least 5 GB free disk space
- [ ] Internet access for downloading packages
- [ ] At least one AI provider API key (Anthropic, OpenAI, or Gemini)

## Server Setup Steps

### 1. System Update
```bash
apt update && apt upgrade -y
```

### 2. Install Docker
```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker
# Add current user to docker group (optional, avoids sudo)
usermod -aG docker $USER
```

### 3. Install Claude Code
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

### 4. Clone Your OpenClaw Fork
```bash
git clone https://github.com/<your-username>/openclaw.git ~/openclaw
cd ~/openclaw
```

### 5. Run Claude Code
```bash
cd ~/openclaw
claude
# Complete browser-based authentication
```

### 6. Deploy with Skill
Inside Claude Code:
```
/server-deploy init
```

## Security Hardening (Recommended)

### Firewall
```bash
apt install -y ufw
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
```

### fail2ban
```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

### SSH Hardening
Edit `/etc/ssh/sshd_config`:
```
PermitRootLogin prohibit-password
PasswordAuthentication no
```
Then: `systemctl restart sshd`

## Port Reference

| Port | Service | Required |
|------|---------|----------|
| 22 | SSH | Yes |
| 80 | HTTP (Nginx) | Recommended |
| 443 | HTTPS (Nginx + SSL) | Recommended |
| 18789 | OpenClaw Gateway | Yes (internal) |
| 18790 | OpenClaw Bridge | Yes (internal) |

Ports 18789 and 18790 do not need to be exposed externally if using Nginx reverse proxy.
