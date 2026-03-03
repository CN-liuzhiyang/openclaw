#!/usr/bin/env python3
"""Health check for OpenClaw deployment."""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error


def run(cmd, timeout=15):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "", 1


def check_container_status():
    """Check if OpenClaw containers are running."""
    output, code = run("docker compose ps --format json 2>/dev/null")
    if code != 0 or not output:
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


def check_port_bindings():
    """Check expected port bindings."""
    output, _ = run("docker compose ps --format json 2>/dev/null")
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

    return {"status": "ok" if ports else "warn", "message": f"Ports: {', '.join(ports) if ports else 'none detected'}"}


def check_resource_usage():
    """Check container resource usage."""
    output, code = run("docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null")
    if code != 0 or not output:
        return {"status": "warn", "message": "Cannot check resource usage"}
    return {"status": "ok", "message": output}


def check_disk_usage():
    """Check Docker disk usage."""
    output, _ = run("docker system df 2>/dev/null")
    if not output:
        return {"status": "warn", "message": "Cannot check Docker disk usage"}
    return {"status": "ok", "message": output}


def main():
    """Run health checks."""
    output_json = "--json" in sys.argv
    wait = "--wait" in sys.argv

    if wait:
        print("Waiting for services to start (max 60s)...")
        for i in range(12):
            result = check_gateway_health()
            if result["status"] == "ok":
                break
            time.sleep(5)

    checks = [
        ("Container Status", check_container_status()),
        ("Gateway Health", check_gateway_health()),
        ("Port Bindings", check_port_bindings()),
        ("Resource Usage", check_resource_usage()),
    ]

    if output_json:
        results = {name: result for name, result in checks}
        print(json.dumps(results, indent=2))
        has_fail = any(r["status"] == "fail" for _, r in checks)
        sys.exit(1 if has_fail else 0)

    status_icons = {"ok": "✓", "warn": "⚠", "fail": "✗"}
    has_fail = False

    print("\n" + "=" * 60)
    print("  OpenClaw Health Check")
    print("=" * 60)

    for name, result in checks:
        icon = status_icons.get(result["status"], "?")
        print(f"\n  {icon} {name}")
        message = result["message"]
        # Handle multiline messages (e.g., docker stats table)
        if "\n" in message:
            for line in message.split("\n"):
                print(f"    {line}")
        else:
            print(f"    {message}")

        # Print container details
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
