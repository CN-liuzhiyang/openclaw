#!/usr/bin/env python3
"""Check server environment readiness for OpenClaw deployment."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys

from common import run


def check_os():
    """Check operating system."""
    info = run("cat /etc/os-release 2>/dev/null")
    if not info:
        return {"status": "warn", "message": "Cannot detect OS", "detail": ""}
    name = ""
    version = ""
    for line in info.split("\n"):
        if line.startswith("PRETTY_NAME="):
            name = line.split("=", 1)[1].strip('"')
        if line.startswith("VERSION_ID="):
            version = line.split("=", 1)[1].strip('"')
    return {"status": "ok", "message": name, "detail": f"Version: {version}"}


def check_node():
    """Check Node.js installation (>= 22)."""
    node_path = shutil.which("node")
    if not node_path:
        return {"status": "fail", "message": "Node.js not installed",
                "detail": "Install Node 22+: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"}
    version_str = run("node --version 2>/dev/null")
    if not version_str:
        return {"status": "fail", "message": "Cannot detect Node.js version", "detail": ""}
    # Parse version: v22.12.0 -> 22
    try:
        major = int(version_str.lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        return {"status": "warn", "message": f"Node.js {version_str} (cannot parse version)", "detail": ""}
    if major < 22:
        return {"status": "fail", "message": f"Node.js {version_str} (requires >= 22)",
                "detail": "Upgrade: curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"}
    return {"status": "ok", "message": f"Node.js {version_str}", "detail": node_path}


def check_pnpm():
    """Check pnpm installation."""
    pnpm_path = shutil.which("pnpm")
    if not pnpm_path:
        return {"status": "fail", "message": "pnpm not installed",
                "detail": "Install: npm install -g pnpm"}
    version = run("pnpm --version 2>/dev/null")
    return {"status": "ok", "message": f"pnpm {version}", "detail": pnpm_path}


def check_docker():
    """Check Docker installation."""
    docker_path = shutil.which("docker")
    if not docker_path:
        return {"status": "fail", "message": "Docker not installed",
                "detail": "Run: curl -fsSL https://get.docker.com | sh"}
    version = run("docker --version")
    running = run("docker info 2>/dev/null")
    if running is None or "Cannot connect" in (running or ""):
        return {"status": "fail", "message": f"Docker installed but not running ({version})",
                "detail": "Run: systemctl start docker"}
    return {"status": "ok", "message": version, "detail": ""}


def check_docker_compose():
    """Check Docker Compose."""
    version = run("docker compose version 2>/dev/null")
    if not version:
        version = run("docker-compose --version 2>/dev/null")
        if not version:
            return {"status": "fail", "message": "Docker Compose not installed",
                    "detail": "Run: apt install -y docker-compose-plugin"}
        return {"status": "warn", "message": f"Legacy: {version}",
                "detail": "Consider upgrading to docker compose plugin"}
    return {"status": "ok", "message": version, "detail": ""}


def check_memory():
    """Check available RAM."""
    meminfo = run("cat /proc/meminfo 2>/dev/null")
    if not meminfo:
        return {"status": "warn", "message": "Cannot check memory", "detail": ""}
    total_kb = 0
    available_kb = 0
    for line in meminfo.split("\n"):
        if line.startswith("MemTotal:"):
            total_kb = int(line.split()[1])
        if line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
    total_gb = total_kb / 1024 / 1024
    available_gb = available_kb / 1024 / 1024
    if total_gb < 1:
        return {"status": "fail", "message": f"Total: {total_gb:.1f} GB (minimum 1 GB)",
                "detail": "OpenClaw requires at least 1 GB RAM"}
    if total_gb < 4:
        return {"status": "warn", "message": f"Total: {total_gb:.1f} GB, Available: {available_gb:.1f} GB",
                "detail": "4 GB recommended for stable operation"}
    return {"status": "ok", "message": f"Total: {total_gb:.1f} GB, Available: {available_gb:.1f} GB", "detail": ""}


def check_disk():
    """Check available disk space."""
    stat = os.statvfs("/")
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
    if free_gb < 2:
        return {"status": "fail", "message": f"Free: {free_gb:.1f} GB / {total_gb:.1f} GB",
                "detail": "At least 2 GB free space needed"}
    if free_gb < 5:
        return {"status": "warn", "message": f"Free: {free_gb:.1f} GB / {total_gb:.1f} GB",
                "detail": "5 GB+ recommended"}
    return {"status": "ok", "message": f"Free: {free_gb:.1f} GB / {total_gb:.1f} GB", "detail": ""}


def check_port(port):
    """Check if a port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            if result == 0:
                proc = run(f"lsof -i :{port} -t 2>/dev/null | head -1")
                proc_name = run(f"lsof -i :{port} 2>/dev/null | tail -1 | awk '{{print $1}}'") if proc else ""
                return {"status": "warn", "message": f"Port {port} in use by {proc_name or 'unknown'}",
                        "detail": f"PID: {proc}"}
            return {"status": "ok", "message": f"Port {port} available", "detail": ""}
    except Exception:
        return {"status": "ok", "message": f"Port {port} available", "detail": ""}


def check_firewall():
    """Check firewall status."""
    ufw = run("ufw status 2>/dev/null")
    if ufw is None:
        return {"status": "warn", "message": "UFW not installed", "detail": "Run: apt install -y ufw"}
    if "inactive" in ufw.lower():
        return {"status": "warn", "message": "UFW installed but inactive",
                "detail": "Consider enabling: ufw --force enable"}
    return {"status": "ok", "message": "UFW active", "detail": ufw.split("\n")[0] if ufw else ""}


def check_git():
    """Check git installation."""
    version = run("git --version 2>/dev/null")
    if not version:
        return {"status": "warn", "message": "Git not installed", "detail": "Run: apt install -y git"}
    return {"status": "ok", "message": version, "detail": ""}


def check_project_files(mode):
    """Check if essential project files exist."""
    if mode == "source":
        files = {
            "package.json": os.path.exists("package.json"),
            "src/": os.path.isdir("src"),
            ".env": os.path.exists(".env"),
            ".env.example": os.path.exists(".env.example"),
        }
        missing = [f for f, exists in files.items() if not exists and f not in (".env",)]
        if missing:
            return {"status": "fail", "message": f"Missing: {', '.join(missing)}",
                    "detail": "Ensure you're in the OpenClaw project directory"}
        env_status = "configured" if files[".env"] else "not configured (will copy from .env.example)"
        dist_exists = os.path.isdir("dist")
        build_note = "dist/ found (built)" if dist_exists else "dist/ not found (needs build)"
        return {"status": "ok", "message": f"Source files present. .env: {env_status}. {build_note}", "detail": ""}
    else:
        files = {
            "docker-compose.yml": os.path.exists("docker-compose.yml"),
            "docker-setup.sh": os.path.exists("docker-setup.sh"),
            "Dockerfile": os.path.exists("Dockerfile"),
            ".env": os.path.exists(".env"),
            ".env.example": os.path.exists(".env.example"),
        }
        missing = [f for f, exists in files.items() if not exists and f != ".env"]
        if missing:
            return {"status": "fail", "message": f"Missing: {', '.join(missing)}",
                    "detail": "Ensure you're in the OpenClaw project directory"}
        env_status = "configured" if files[".env"] else "not configured (will copy from .env.example)"
        return {"status": "ok", "message": f"All project files found. .env: {env_status}", "detail": ""}


def check_existing_deployment(mode):
    """Check if OpenClaw is already deployed."""
    if mode == "source":
        # Check systemd
        systemd_out = run("systemctl is-active openclaw-gateway 2>/dev/null")
        if systemd_out and systemd_out.strip() == "active":
            return {"status": "info", "message": "Existing source deployment found (systemd, active)", "detail": ""}
        # Check pm2
        pm2_out = run("pm2 describe openclaw-gateway 2>/dev/null", check=True)
        if pm2_out is not None and "online" in pm2_out.lower():
            return {"status": "info", "message": "Existing source deployment found (pm2, online)", "detail": ""}
        return {"status": "info", "message": "No existing source deployment found", "detail": "Ready for fresh deployment"}
    else:
        containers = run("docker compose ps --format json 2>/dev/null")
        if not containers:
            return {"status": "info", "message": "No existing Docker deployment found",
                    "detail": "Ready for fresh deployment"}
        return {"status": "info", "message": "Existing Docker deployment detected",
                "detail": containers[:200]}


def main():
    parser = argparse.ArgumentParser(description="Check server environment for OpenClaw")
    parser.add_argument("--mode", choices=["source", "docker"], default="source",
                        help="Deployment mode to check for (default: source)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    mode = args.mode

    # Build check list based on mode
    checks = [("Operating System", check_os())]

    if mode == "source":
        checks.append(("Node.js", check_node()))
        checks.append(("pnpm", check_pnpm()))
    else:
        checks.append(("Docker", check_docker()))
        checks.append(("Docker Compose", check_docker_compose()))

    checks.extend([
        ("Git", check_git()),
        ("Memory (RAM)", check_memory()),
        ("Disk Space", check_disk()),
        ("Port 18789 (Gateway)", check_port(18789)),
        ("Port 18790 (Bridge)", check_port(18790)),
        ("Port 80 (HTTP)", check_port(80)),
        ("Port 443 (HTTPS)", check_port(443)),
        ("Firewall (UFW)", check_firewall()),
        ("Project Files", check_project_files(mode)),
        ("Existing Deployment", check_existing_deployment(mode)),
    ])

    if args.json:
        results = {name: result for name, result in checks}
        print(json.dumps(results, indent=2))
        return

    status_icons = {"ok": "\u2713", "warn": "\u26a0", "fail": "\u2717", "info": "\u2139"}
    has_failures = False
    has_warnings = False

    print("\n" + "=" * 60)
    print(f"  OpenClaw Server Environment Check (mode: {mode})")
    print("=" * 60)

    for name, result in checks:
        icon = status_icons.get(result["status"], "?")
        print(f"\n  {icon} {name}")
        print(f"    {result['message']}")
        if result.get("detail"):
            print(f"    {result['detail']}")
        if result["status"] == "fail":
            has_failures = True
        if result["status"] == "warn":
            has_warnings = True

    print("\n" + "=" * 60)
    if has_failures:
        print("  Result: FAIL — Critical issues found. Fix before deploying.")
        sys.exit(1)
    elif has_warnings:
        print("  Result: WARN — Some warnings. Deployment possible but review recommended.")
        sys.exit(0)
    else:
        print("  Result: OK — Server is ready for OpenClaw deployment.")
        sys.exit(0)


if __name__ == "__main__":
    main()
