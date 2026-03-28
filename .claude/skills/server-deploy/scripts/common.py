#!/usr/bin/env python3
"""Shared utilities for OpenClaw server-deploy scripts."""

import os
import shutil
import subprocess
import sys


def _get_env_with_proxy():
    """Return a copy of os.environ that includes proxy settings if available.

    Detects mihomo/Clash proxy at 127.0.0.1:7890 and injects http_proxy/https_proxy
    when not already set. This is critical for China-mainland servers where direct
    access to GitHub, npm, etc. is slow or blocked.
    """
    env = os.environ.copy()
    if env.get("http_proxy") or env.get("HTTP_PROXY"):
        return env  # already configured

    # Auto-detect local proxy (mihomo / Clash Meta)
    import socket
    proxy_addr = "http://127.0.0.1:7890"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", 7890)) == 0:
                env.setdefault("http_proxy", proxy_addr)
                env.setdefault("https_proxy", proxy_addr)
                env.setdefault("HTTP_PROXY", proxy_addr)
                env.setdefault("HTTPS_PROXY", proxy_addr)
    except OSError:
        pass
    return env


def proxy_env():
    """Return proxy env dict (subset) for display/logging. Empty dict if no proxy."""
    env = _get_env_with_proxy()
    proxy = env.get("http_proxy") or env.get("HTTP_PROXY")
    if proxy:
        return {"http_proxy": proxy, "https_proxy": env.get("https_proxy", proxy)}
    return {}


def run(cmd, capture=True, check=False, timeout=120):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True,
            timeout=timeout, env=_get_env_with_proxy(),
        )
        if check and result.returncode != 0:
            return None
        if capture:
            return result.stdout.strip()
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def run_verbose(cmd, timeout=300, check=True):
    """Run a shell command with output printed."""
    print(f"  $ {cmd}")
    env = _get_env_with_proxy()
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[-20:]:
            print(f"    {line}")
    if check and result.returncode != 0:
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n")[-10:]:
                print(f"    Error: {line}", file=sys.stderr)
        return False
    return True


def detect_mode(cli_mode=None):
    """Detect deployment mode.

    Priority:
    1. CLI --mode argument
    2. systemd service file exists -> source
    3. pm2 has openclaw process -> source
    4. docker compose has running containers -> docker
    5. Default: source
    """
    if cli_mode:
        return cli_mode

    # Check systemd
    if os.path.exists("/etc/systemd/system/openclaw-gateway.service"):
        return "source"

    # Check pm2
    pm2_check = run("pm2 describe openclaw-gateway 2>/dev/null", check=True)
    if pm2_check is not None and "online" in pm2_check.lower():
        return "source"

    # Check docker
    docker_check = run("docker compose ps --format json 2>/dev/null")
    if docker_check and "openclaw" in docker_check.lower():
        return "docker"

    return "source"


def detect_pm(cli_pm=None):
    """Detect process manager.

    Priority:
    1. CLI --pm argument
    2. systemd service exists -> systemd
    3. pm2 has openclaw process -> pm2
    4. Default: systemd
    """
    if cli_pm:
        return cli_pm

    if os.path.exists("/etc/systemd/system/openclaw-gateway.service"):
        return "systemd"

    pm2_check = run("pm2 describe openclaw-gateway 2>/dev/null", check=True)
    if pm2_check is not None:
        return "pm2"

    return "systemd"


def get_project_dir():
    """Get the OpenClaw project root directory."""
    # Walk up from script location to find package.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # scripts/ -> server-deploy/ -> skills/ -> .claude/ -> project root
    candidate = os.path.normpath(os.path.join(script_dir, "..", "..", "..", ".."))
    if os.path.exists(os.path.join(candidate, "package.json")):
        return candidate
    # Fallback: current working directory
    return os.getcwd()


def get_config_dir():
    """Get OpenClaw config directory from .env or default."""
    project = get_project_dir()
    env_file = os.path.join(project, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENCLAW_CONFIG_DIR="):
                    path = line.split("=", 1)[1].strip('"').strip("'")
                    return os.path.expanduser(path)
    return os.path.expanduser("~/.openclaw")


def restart_service(mode, pm):
    """Restart the openclaw-gateway service."""
    if mode == "docker":
        return run_verbose("docker compose down && docker compose up -d openclaw-gateway")
    elif pm == "systemd":
        return run_verbose("sudo systemctl restart openclaw-gateway")
    elif pm == "pm2":
        return run_verbose("pm2 restart openclaw-gateway")
    return False


def stop_service(mode, pm):
    """Stop the openclaw-gateway service."""
    if mode == "docker":
        return run_verbose("docker compose down")
    elif pm == "systemd":
        return run_verbose("sudo systemctl stop openclaw-gateway")
    elif pm == "pm2":
        return run_verbose("pm2 stop openclaw-gateway")
    return False


def start_service(mode, pm):
    """Start the openclaw-gateway service."""
    if mode == "docker":
        return run_verbose("docker compose up -d openclaw-gateway")
    elif pm == "systemd":
        return run_verbose("sudo systemctl start openclaw-gateway")
    elif pm == "pm2":
        project_dir = get_project_dir()
        ecosystem = os.path.join(project_dir, "ecosystem.config.cjs")
        if os.path.exists(ecosystem):
            return run_verbose(f"pm2 start '{ecosystem}'")
        return run_verbose(
            f"pm2 start '{os.path.join(project_dir, 'dist/index.js')}' "
            f"--name openclaw-gateway -- gateway --bind lan --port 18789"
        )
    return False


def parse_mode_args(parser):
    """Add common --mode and --pm arguments to an argparse parser."""
    parser.add_argument(
        "--mode", choices=["source", "docker"], default=None,
        help="Deployment mode (auto-detected if not set)"
    )
    parser.add_argument(
        "--pm", choices=["systemd", "pm2"], default=None,
        help="Process manager for source mode (auto-detected if not set)"
    )
    return parser
