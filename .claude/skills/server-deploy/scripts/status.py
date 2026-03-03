#!/usr/bin/env python3
"""Show OpenClaw service status (source and Docker modes)."""

import argparse
import json
import os
import subprocess
import sys

from common import detect_mode, detect_pm, run


def status_docker():
    """Gather status for Docker deployment."""
    sections = {}

    ps_output = run("docker compose ps 2>/dev/null")
    sections["containers"] = ps_output or "No containers found"

    stats_output = run(
        "docker stats --no-stream --format "
        "'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>/dev/null"
    )
    sections["resources"] = stats_output or "Cannot fetch resource stats"

    uptime_output = run("docker compose ps --format json 2>/dev/null")
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

    health_output = run(
        "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/healthz 2>/dev/null"
    )
    sections["gateway_health"] = (
        "Healthy (HTTP 200)" if health_output == "200"
        else f"Unhealthy (HTTP {health_output or 'no response'})"
    )

    logs_output = run("docker compose logs --tail 5 openclaw-gateway 2>/dev/null")
    sections["recent_logs"] = logs_output[:1000] if logs_output else "No logs available"

    return sections


def status_source(pm):
    """Gather status for source deployment."""
    sections = {}

    if pm == "systemd":
        svc = run("systemctl status openclaw-gateway --no-pager 2>/dev/null")
        sections["service"] = svc or "Service not found (systemctl status failed)"

        props = run(
            "systemctl show openclaw-gateway "
            "--property=ActiveState,SubState,MainPID,MemoryCurrent,ActiveEnterTimestamp "
            "--no-pager 2>/dev/null"
        )
        sections["details"] = props or "No details"

    elif pm == "pm2":
        pm2_out = run("pm2 describe openclaw-gateway 2>/dev/null")
        sections["service"] = pm2_out or "Process not found in pm2"

        pm2_monit = run("pm2 monit --no-stream 2>/dev/null")
        if pm2_monit:
            sections["details"] = pm2_monit[:500]
        else:
            sections["details"] = ""
    else:
        pid = run("pgrep -f 'node.*dist/index.js.*gateway' 2>/dev/null")
        if pid:
            pid_val = pid.split()[0]
            ps_info = run(f"ps -p {pid_val} -o pid,user,%cpu,%mem,vsz,rss,etime,cmd --no-headers 2>/dev/null")
            sections["service"] = f"Running (PID: {pid_val})"
            sections["details"] = ps_info or ""
        else:
            sections["service"] = "Not running"
            sections["details"] = ""

    # Gateway health (same for all)
    health_output = run(
        "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18789/healthz 2>/dev/null"
    )
    sections["gateway_health"] = (
        "Healthy (HTTP 200)" if health_output == "200"
        else f"Unhealthy (HTTP {health_output or 'no response'})"
    )

    # Logs
    if pm == "systemd":
        logs = run("journalctl -u openclaw-gateway --no-pager -n 5 2>/dev/null")
        sections["recent_logs"] = logs[:1000] if logs else "No logs available"
    elif pm == "pm2":
        logs = run("pm2 logs openclaw-gateway --nostream --lines 5 2>/dev/null")
        sections["recent_logs"] = logs[:1000] if logs else "No logs available"
    else:
        sections["recent_logs"] = "No log source available (not managed by systemd/pm2)"

    return sections


def print_sections(sections, mode, pm=None):
    """Pretty-print status sections."""
    print("\n" + "=" * 60)
    label = f"mode: {mode}"
    if mode == "source" and pm:
        label += f", pm: {pm}"
    print(f"  OpenClaw Service Status ({label})")
    print("=" * 60)

    for key, value in sections.items():
        title = key.replace("_", " ").title()
        print(f"\n  [{title}]")
        for line in value.split("\n"):
            print(f"  {line}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Show OpenClaw status")
    parser.add_argument("--mode", choices=["source", "docker"], default=None)
    parser.add_argument("--pm", choices=["systemd", "pm2"], default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    mode = detect_mode(args.mode)
    pm = detect_pm(args.pm)

    # Config info (common)
    config_dir = os.path.expanduser("~/.openclaw")
    env_file = ".env"
    config_info = []
    if os.path.exists(config_dir):
        config_info.append(f"Config: {config_dir}")
        config_size = run(f"du -sh '{config_dir}' 2>/dev/null")
        if config_size:
            config_info.append(f"Size: {config_size}")
    if os.path.exists(env_file):
        config_info.append(f"Env: {os.path.abspath(env_file)}")

    if mode == "docker":
        sections = status_docker()
    else:
        sections = status_source(pm)

    sections["config"] = "\n  ".join(config_info) if config_info else "Not found"

    if args.json:
        print(json.dumps(sections, indent=2))
        return

    print_sections(sections, mode, pm)


if __name__ == "__main__":
    main()
