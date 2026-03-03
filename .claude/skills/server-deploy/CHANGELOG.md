# Changelog

All notable changes to the server-deploy skill will be documented in this file.

## [1.0.0] - 2026-03-03

### Added
- Initial release of server-deploy skill
- Environment check script (`check_env.py`) — OS, Docker, ports, RAM, disk
- Deployment script (`deploy.py`) — supports docker-setup.sh and manual compose
- Health check script (`health_check.py`) — container status, gateway health, resources
- Backup script (`backup.py`) — timestamped archives of ~/.openclaw
- Update script (`update.py`) — pull upstream, rebuild, restart with rollback support
- Rollback script (`rollback.py`) — restore from backup archives
- Nginx setup script (`setup_nginx.py`) — reverse proxy configuration from template
- SSL setup script (`setup_ssl.py`) — Let's Encrypt via certbot
- Status script (`status.py`) — comprehensive service status overview
- Nginx config template with WebSocket support
- Environment variable template
- Server preparation checklist reference
