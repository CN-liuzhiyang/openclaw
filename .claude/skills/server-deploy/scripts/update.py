#!/usr/bin/env python3
"""Update OpenClaw to the latest version (source and Docker modes)."""

import argparse
import os
import subprocess
import sys

from common import detect_mode, detect_pm, run_verbose, restart_service


def main():
    parser = argparse.ArgumentParser(description="Update OpenClaw")
    parser.add_argument("--mode", choices=["source", "docker"], default=None)
    parser.add_argument("--pm", choices=["systemd", "pm2"], default=None)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    mode = detect_mode(args.mode)
    pm = detect_pm(args.pm)

    print("\n" + "=" * 60)
    print(f"  OpenClaw Update (mode: {mode})")
    print("=" * 60)

    # Step 1: Backup
    if not args.no_backup:
        print("\n[1/5] Creating backup before update...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backup_script = os.path.join(script_dir, "backup.py")
        if os.path.exists(backup_script):
            if not run_verbose(f"python3 '{backup_script}'", check=False):
                print("  Warning: Backup may have issues, continuing anyway...")
        else:
            print("  Warning: Backup script not found, skipping...")
    else:
        print("\n[1/5] Backup skipped (--no-backup)")

    # Step 2: Pull latest changes
    print("\n[2/5] Pulling latest changes from upstream...")
    if not run_verbose("git fetch upstream 2>/dev/null || git fetch origin"):
        print("  Failed to fetch updates", file=sys.stderr)
        sys.exit(1)

    current_branch = subprocess.run(
        "git branch --show-current", shell=True, capture_output=True, text=True
    ).stdout.strip() or "main"

    if not run_verbose(f"git merge upstream/{current_branch} --no-edit 2>/dev/null", check=False):
        if not run_verbose(f"git pull origin {current_branch} --no-edit", check=False):
            print("  Warning: Could not merge upstream changes. Continuing with current code...")

    # Step 3: Rebuild
    if mode == "source":
        print("\n[3/5] Rebuilding from source...")
        if not run_verbose("pnpm install --frozen-lockfile 2>/dev/null || pnpm install", timeout=300):
            print("  Failed to install dependencies", file=sys.stderr)
            sys.exit(1)
        if not run_verbose("pnpm build", timeout=600):
            print("  Failed to build", file=sys.stderr)
            sys.exit(1)
    else:
        print("\n[3/5] Rebuilding Docker image...")
        if not run_verbose("docker compose build", timeout=600):
            print("  Failed to build image", file=sys.stderr)
            sys.exit(1)

    # Step 4: Restart services
    print("\n[4/5] Restarting services...")
    if not restart_service(mode, pm):
        print("  Failed to restart services", file=sys.stderr)
        sys.exit(1)

    # Step 5: Health check
    print("\n[5/5] Running health check...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        result = subprocess.run(
            f"python3 '{health_script}' --wait --mode {mode}",
            shell=True, timeout=120,
        )
        if result.returncode != 0:
            print("\n  ⚠ Health check failed after update!")
            print("  Run '/server-deploy rollback' to restore previous version.")
            sys.exit(1)
    else:
        print("  Health check script not found, skipping...")

    print("\n" + "=" * 60)
    print("  ✓ Update completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
