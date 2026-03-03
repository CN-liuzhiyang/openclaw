#!/usr/bin/env python3
"""Show OpenClaw service status."""

import json
import os
import subprocess
import sys


def run(cmd, timeout=15):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "", 1


def main():
    output_json = "--json" in sys.argv

    sections = {}

    # Container status
    ps_output, _ = run("docker compose ps 2>/dev/null")
    sections["containers"] = ps_output or "No containers found"

    # Resource usage
    stats_output, _ = run("docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>/dev/null")
    sections["resources"] = stats_output or "Cannot fetch resource stats"

    # Uptime
    uptime_output, _ = run("docker compose ps --format json 2>/dev/null")
    if uptime_output:
        uptimes = []
        for line in uptime_output.strip().split("\n"):
            if line.strip():
                try:
                    c = json.loads(line)
                    uptimes.append(f"  {c.get('Name', 'unknown')}: {c.get('Status', 'unknown')}")
                except json.JSONDecodeError:
                    continue
        sections["uptime"] = "\n".join(uptimes) if uptimes else "No data"
    else:
        sections["uptime"] = "No data"

    # Gateway health
    health_output, code = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/healthz 2>/dev/null")
    if health_output == "200":
        sections["gateway_health"] = "Healthy (HTTP 200)"
    else:
        sections["gateway_health"] = f"Unhealthy (HTTP {health_output or 'no response'})"

    # Config info
    config_dir = os.path.expanduser("~/.openclaw")
    env_file = ".env"
    config_info = []
    if os.path.exists(config_dir):
        config_info.append(f"Config: {config_dir}")
        config_size, _ = run(f"du -sh '{config_dir}' 2>/dev/null")
        if config_size:
            config_info.append(f"Size: {config_size}")
    if os.path.exists(env_file):
        config_info.append(f"Env: {os.path.abspath(env_file)}")
    sections["config"] = "\n  ".join(config_info) if config_info else "Not found"

    # Recent logs (last 5 lines)
    logs_output, _ = run("docker compose logs --tail 5 openclaw-gateway 2>/dev/null")
    sections["recent_logs"] = logs_output[:1000] if logs_output else "No logs available"

    if output_json:
        print(json.dumps(sections, indent=2))
        return

    print("\n" + "=" * 60)
    print("  OpenClaw Service Status")
    print("=" * 60)

    print("\n  [Containers]")
    for line in sections["containers"].split("\n"):
        print(f"  {line}")

    print("\n  [Resources]")
    for line in sections["resources"].split("\n"):
        print(f"  {line}")

    print("\n  [Uptime]")
    print(f"  {sections['uptime']}")

    print(f"\n  [Gateway Health]")
    print(f"  {sections['gateway_health']}")

    print(f"\n  [Configuration]")
    print(f"  {sections['config']}")

    print(f"\n  [Recent Logs]")
    for line in sections["recent_logs"].split("\n")[-5:]:
        print(f"  {line}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
