#!/usr/bin/env python3
"""Deploy OpenClaw via source build or Docker Compose."""

import argparse
import os
import shutil
import subprocess
import sys

from common import (
    detect_mode, detect_pm, get_project_dir, get_config_dir,
    run, run_verbose, start_service, proxy_env,
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
    p = proxy_env()
    if p:
        print(f"    (proxy detected: {p.get('http_proxy', 'none')})")
    return run_verbose("pnpm install --frozen-lockfile 2>/dev/null || pnpm install", timeout=600)


def build_project():
    """Run pnpm build and pnpm ui:build.

    The A2UI bundling step uses `pnpm dlx rolldown` which may fail when a
    China-mainland npm mirror (e.g. Tencent mirrors) is configured as the
    default registry — the mirror often returns ECONNRESET for rolldown.
    We work around this by temporarily setting npm_config_registry to the
    official npmjs.org registry; the proxy env (auto-detected in common.py)
    ensures connectivity.
    """
    print("\n  Building project...")
    # Use official registry for pnpm dlx calls (rolldown) to avoid mirror issues
    if not run_verbose(
        "npm_config_registry=https://registry.npmjs.org pnpm build", timeout=600
    ):
        return False

    # Build Control UI assets (required for /health endpoint and web dashboard)
    print("\n  Building Control UI...")
    if not run_verbose(
        "npm_config_registry=https://registry.npmjs.org pnpm ui:build", timeout=300
    ):
        print("  ⚠ UI build failed (non-critical, gateway will still work)")
    return True


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


def configure_gateway():
    """Set essential gateway config values for first-time deployment.

    Without these, the gateway exits immediately with:
    - 'Missing config. Run openclaw setup or set gateway.mode=local'
    - 'non-loopback Control UI requires gateway.controlUi.allowedOrigins'
    """
    project_dir = get_project_dir()
    node = shutil.which("node") or "node"
    cli = os.path.join(project_dir, "dist", "index.js")

    if not os.path.exists(cli):
        print("  ⚠ dist/index.js not found, skipping gateway config")
        return

    # Read .env to check bind mode
    bind = "lan"
    env_file = os.path.join(project_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("OPENCLAW_GATEWAY_BIND="):
                    bind = line.strip().split("=", 1)[1].strip('"').strip("'") or bind

    config_dir = get_config_dir()
    config_file = os.path.join(config_dir, "openclaw.json")

    # Only configure if no config exists yet (fresh deployment)
    if os.path.exists(config_file):
        print("  Gateway config already exists, skipping auto-configure")
        return

    print("\n  Configuring gateway defaults...")
    run_verbose(f"{node} {cli} config set gateway.mode local", check=False)
    # For non-loopback binds, allow Host-header origin fallback for Control UI
    if bind != "loopback":
        run_verbose(
            f"{node} {cli} config set "
            "gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback true",
            check=False,
        )


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

    # Configure gateway defaults (must happen after build, before start)
    configure_gateway()

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
    print("\n[1/4] Checking environment configuration...")
    p = proxy_env()
    if p:
        print(f"  Proxy detected: {p.get('http_proxy', 'none')}")
    setup_env()

    # Step 2: Deploy
    print("\n[2/4] Deploying OpenClaw...")
    if mode == "source":
        success = deploy_source(pm)
    else:
        success = deploy_docker()

    if not success:
        print("\n  ✗ Deployment failed!", file=sys.stderr)
        sys.exit(1)

    # Step 3: Wait for gateway startup
    print("\n[3/4] Waiting for gateway to start (up to 60s)...")
    import time
    for i in range(12):
        time.sleep(5)
        port_check = run(f"ss -tlnp 2>/dev/null | grep :18789")
        if port_check:
            print(f"  Gateway port listening after ~{(i+1)*5}s")
            break
    else:
        print("  ⚠ Gateway port not detected after 60s — check logs")

    # Step 4: Health check
    print("\n[4/4] Running health check...")
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
