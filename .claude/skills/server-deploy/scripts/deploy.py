#!/usr/bin/env python3
"""Deploy OpenClaw via source build or Docker Compose."""

import argparse
import os
import shutil
import subprocess
import sys

from common import (
    detect_mode, detect_pm, get_project_dir, get_config_dir,
    run, run_verbose, start_service,
)


def setup_env():
    """Ensure .env file exists with required values."""
    if os.path.exists(".env"):
        print("  .env file already exists")
        return True

    if not os.path.exists(".env.example"):
        print("  Warning: .env.example not found", file=sys.stderr)
        return False

    with open(".env.example") as f:
        content = f.read()
    with open(".env", "w") as f:
        f.write(content)

    print("  Created .env from .env.example")
    print("  ⚠ You need to configure API keys in .env before deploying!")
    return True


# ---------------------------------------------------------------------------
# Source deployment
# ---------------------------------------------------------------------------

def install_dependencies():
    """Run pnpm install."""
    print("\n  Installing dependencies with pnpm...")
    return run_verbose("pnpm install --frozen-lockfile 2>/dev/null || pnpm install", timeout=300)


def build_project():
    """Run pnpm build."""
    print("\n  Building project...")
    return run_verbose("pnpm build", timeout=600)


def install_systemd_service():
    """Generate and install a systemd service file."""
    project_dir = get_project_dir()
    config_dir = get_config_dir()
    workspace_dir = os.path.join(config_dir, "workspace")
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"

    # Read .env for bind/port overrides
    bind = "lan"
    port = "18789"
    env_file = os.path.join(project_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENCLAW_GATEWAY_BIND="):
                    bind = line.split("=", 1)[1].strip('"').strip("'") or bind
                if line.startswith("OPENCLAW_GATEWAY_PORT="):
                    port = line.split("=", 1)[1].strip('"').strip("'") or port

    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "templates", "openclaw-gateway.service"
    )
    with open(template_path) as f:
        content = f.read()

    content = (
        content
        .replace("{{USER}}", user)
        .replace("{{PROJECT_DIR}}", project_dir)
        .replace("{{CONFIG_DIR}}", config_dir)
        .replace("{{WORKSPACE_DIR}}", workspace_dir)
        .replace("{{BIND}}", bind)
        .replace("{{PORT}}", port)
    )

    service_path = "/etc/systemd/system/openclaw-gateway.service"
    print(f"\n  Installing systemd service -> {service_path}")

    with open(service_path, "w") as f:
        f.write(content)

    run_verbose("sudo systemctl daemon-reload")
    run_verbose("sudo systemctl enable openclaw-gateway")
    return True


def install_pm2_service():
    """Generate and install a pm2 ecosystem config, then start."""
    project_dir = get_project_dir()
    config_dir = get_config_dir()
    workspace_dir = os.path.join(config_dir, "workspace")

    template_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "templates", "ecosystem.config.cjs"
    )
    with open(template_path) as f:
        content = f.read()

    content = (
        content
        .replace("{{PROJECT_DIR}}", project_dir)
        .replace("{{CONFIG_DIR}}", config_dir)
        .replace("{{WORKSPACE_DIR}}", workspace_dir)
    )

    eco_path = os.path.join(project_dir, "ecosystem.config.cjs")
    print(f"\n  Writing pm2 ecosystem config -> {eco_path}")

    with open(eco_path, "w") as f:
        f.write(content)

    # Ensure log directory exists
    os.makedirs(os.path.join(config_dir, "logs"), exist_ok=True)
    return True


def deploy_source(pm):
    """Deploy OpenClaw from source code."""
    print("  Deployment mode: SOURCE")
    print(f"  Process manager: {pm}")

    # Install deps & build
    if not install_dependencies():
        return False
    if not build_project():
        return False

    # Ensure config dirs exist
    config_dir = get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(os.path.join(config_dir, "workspace"), exist_ok=True)

    # Setup process manager
    if pm == "systemd":
        if not install_systemd_service():
            return False
    elif pm == "pm2":
        if not shutil.which("pm2"):
            print("\n  pm2 not found, installing globally...")
            run_verbose("npm install -g pm2")
        if not install_pm2_service():
            return False

    # Start service
    print("\n  Starting OpenClaw gateway...")
    return start_service("source", pm)


# ---------------------------------------------------------------------------
# Docker deployment
# ---------------------------------------------------------------------------

def deploy_docker():
    """Deploy using Docker Compose."""
    print("  Deployment mode: DOCKER")

    if os.path.exists("docker-setup.sh"):
        print("\n  Using official docker-setup.sh...")
        run_verbose("chmod +x docker-setup.sh", check=False)
        success = subprocess.run("./docker-setup.sh", shell=True, timeout=900).returncode == 0
        if success:
            return True
        print("  docker-setup.sh failed, falling back to manual deployment...")

    print("\n  Building Docker image...")
    if not run_verbose("docker compose build", timeout=900):
        return False

    print("\n  Starting OpenClaw gateway...")
    return run_verbose("docker compose up -d openclaw-gateway")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deploy OpenClaw")
    parser.add_argument("--mode", choices=["source", "docker"], default=None,
                        help="Deployment mode (default: auto-detect, prefers source)")
    parser.add_argument("--pm", choices=["systemd", "pm2"], default=None,
                        help="Process manager for source mode (default: systemd)")
    args = parser.parse_args()

    mode = args.mode or "source"
    pm = args.pm or "systemd"

    print("\n" + "=" * 60)
    print("  OpenClaw Deployment")
    print("=" * 60)

    # Verify project directory
    if mode == "source" and not os.path.exists("package.json"):
        print("  Error: package.json not found.", file=sys.stderr)
        print("  Make sure you're in the OpenClaw project directory.", file=sys.stderr)
        sys.exit(1)
    if mode == "docker" and not os.path.exists("docker-compose.yml"):
        print("  Error: docker-compose.yml not found.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Setup .env
    print("\n[1/3] Checking environment configuration...")
    setup_env()

    # Step 2: Deploy
    print("\n[2/3] Deploying OpenClaw...")
    if mode == "source":
        success = deploy_source(pm)
    else:
        success = deploy_docker()

    if not success:
        print("\n  ✗ Deployment failed!", file=sys.stderr)
        sys.exit(1)

    # Step 3: Health check
    print("\n[3/3] Running health check...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        subprocess.run(
            f"python3 '{health_script}' --wait --mode {mode}",
            shell=True, timeout=120,
        )

    print("\n" + "=" * 60)
    print("  ✓ OpenClaw deployed successfully!")
    print("  Access the web UI at http://<server-ip>:18789")
    if mode == "source" and pm == "systemd":
        print("  Manage: sudo systemctl {start|stop|restart|status} openclaw-gateway")
    elif mode == "source" and pm == "pm2":
        print("  Manage: pm2 {start|stop|restart|status} openclaw-gateway")
    print("=" * 60)


if __name__ == "__main__":
    main()
