#!/usr/bin/env python3
"""Health check for OpenClaw deployment (source and Docker modes)."""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

from common import detect_mode, run


def check_container_status():
    """Check if OpenClaw Docker containers are running."""
    output = run("docker compose ps --format json 2>/dev/null")
    if not output:
        return {"status": "fail", "message": "Cannot query Docker containers"}

    containers = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:
                c = json.loads(line)
                containers.append({
                    "name": c.get("Name", c.get("Service", "unknown")),
                    "state": c.get("State", "unknown"),
                    "status": c.get("Status", "unknown"),
                    "health": c.get("Health", ""),
                })
            except json.JSONDecodeError:
                continue

    if not containers:
        return {"status": "fail", "message": "No containers found"}

    running = [c for c in containers if c["state"] == "running"]
    return {
        "status": "ok" if running else "fail",
        "message": f"{len(running)}/{len(containers)} containers running",
        "containers": containers,
    }


def check_process_status():
    """Check if OpenClaw node process is running (source mode)."""
    # Check systemd first
    systemd_status = run("systemctl is-active openclaw-gateway 2>/dev/null")
    if systemd_status and systemd_status.strip() == "active":
        detail = run("systemctl show openclaw-gateway --property=MainPID,ActiveEnterTimestamp --no-pager 2>/dev/null")
        return {"status": "ok", "message": "Process running (systemd: active)", "detail": detail or ""}

    # Check pm2
    pm2_status = run("pm2 jlist 2>/dev/null")
    if pm2_status:
        try:
            procs = json.loads(pm2_status)
            for p in procs:
                if p.get("name") == "openclaw-gateway":
                    status = p.get("pm2_env", {}).get("status", "unknown")
                    pid = p.get("pid", "?")
                    mem = p.get("monit", {}).get("memory", 0)
                    mem_mb = mem / (1024 * 1024) if mem else 0
                    return {
                        "status": "ok" if status == "online" else "fail",
                        "message": f"Process {status} (pm2, PID: {pid}, Mem: {mem_mb:.0f}MB)",
                    }
        except (json.JSONDecodeError, TypeError):
            pass

    # Check raw process
    pgrep = run("pgrep -f 'node.*dist/index.js.*gateway' 2>/dev/null")
    if pgrep:
        return {"status": "ok", "message": f"Process running (PID: {pgrep.split()[0]})"}

    return {"status": "fail", "message": "OpenClaw gateway process not found"}


def check_gateway_health(port=18789, retries=3):
    """Check the gateway health endpoint."""
    url = f"http://127.0.0.1:{port}/healthz"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return {"status": "ok", "message": f"Gateway healthy (port {port})"}
        except (urllib.error.URLError, urllib.error.HTTPError, ConnectionError, OSError):
            if attempt < retries - 1:
                time.sleep(2)
                continue

    return {"status": "fail", "message": f"Gateway not responding on port {port}"}


def check_port_bindings_docker():
    """Check expected port bindings (Docker mode)."""
    output = run("docker compose ps --format json 2>/dev/null")
    if not output:
        return {"status": "warn", "message": "Cannot check port bindings"}

    ports = []
    for line in output.strip().split("\n"):
        if line.strip():
            try:
                c = json.loads(line)
                port_list = c.get("Publishers", [])
                for p in port_list:
                    if isinstance(p, dict):
                        ports.append(f"{p.get('PublishedPort', '?')}->{p.get('TargetPort', '?')}")
            except (json.JSONDecodeError, TypeError):
                continue

    return {
        "status": "ok" if ports else "warn",
        "message": f"Ports: {', '.join(ports) if ports else 'none detected'}",
    }


def check_port_listening(port=18789):
    """Check if the gateway port is listening (source mode)."""
    output = run(f"ss -tlnp 2>/dev/null | grep :{port}")
    if output:
        return {"status": "ok", "message": f"Port {port} listening"}
    return {"status": "warn", "message": f"Port {port} not listening"}


def check_resource_usage_docker():
    """Check container resource usage."""
    output = run(
        "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null"
    )
    if not output:
        return {"status": "warn", "message": "Cannot check resource usage"}
    return {"status": "ok", "message": output}


def main():
    parser = argparse.ArgumentParser(description="OpenClaw health check")
    parser.add_argument("--mode", choices=["source", "docker"], default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    mode = detect_mode(args.mode)

    if args.wait:
        print("Waiting for services to start (max 60s)...")
        for i in range(12):
            result = check_gateway_health()
            if result["status"] == "ok":
                break
            time.sleep(5)

    # Build checks
    checks = []
    if mode == "docker":
        checks.append(("Container Status", check_container_status()))
        checks.append(("Gateway Health", check_gateway_health()))
        checks.append(("Port Bindings", check_port_bindings_docker()))
        checks.append(("Resource Usage", check_resource_usage_docker()))
    else:
        checks.append(("Process Status", check_process_status()))
        checks.append(("Gateway Health", check_gateway_health()))
        checks.append(("Port Listening", check_port_listening()))

    if args.json:
        results = {name: result for name, result in checks}
        print(json.dumps(results, indent=2))
        has_fail = any(r["status"] == "fail" for _, r in checks)
        sys.exit(1 if has_fail else 0)

    status_icons = {"ok": "\u2713", "warn": "\u26a0", "fail": "\u2717"}
    has_fail = False

    print("\n" + "=" * 60)
    print(f"  OpenClaw Health Check (mode: {mode})")
    print("=" * 60)

    for name, result in checks:
        icon = status_icons.get(result["status"], "?")
        print(f"\n  {icon} {name}")
        message = result["message"]
        if "\n" in message:
            for line in message.split("\n"):
                print(f"    {line}")
        else:
            print(f"    {message}")
        if result.get("detail"):
            print(f"    {result['detail']}")
        if "containers" in result:
            for c in result["containers"]:
                health_str = f" ({c['health']})" if c.get("health") else ""
                print(f"      - {c['name']}: {c['state']} {c['status']}{health_str}")
        if result["status"] == "fail":
            has_fail = True

    print("\n" + "=" * 60)
    if has_fail:
        print("  Result: UNHEALTHY — Some services are not working properly.")
        sys.exit(1)
    else:
        print("  Result: HEALTHY — All services are running normally.")
        sys.exit(0)


if __name__ == "__main__":
    main()
