#!/usr/bin/env python3
"""Update OpenClaw to the latest version."""

import os
import subprocess
import sys


def run(cmd, timeout=300, check=True):
    """Run a shell command."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()[:200]}")
    if check and result.returncode != 0:
        print(f"    Error: {result.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def main():
    skip_backup = "--no-backup" in sys.argv

    print("\n" + "=" * 60)
    print("  OpenClaw Update")
    print("=" * 60)

    # Step 1: Backup
    if not skip_backup:
        print("\n[1/5] Creating backup before update...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backup_script = os.path.join(script_dir, "backup.py")
        if os.path.exists(backup_script):
            if not run(f"python3 '{backup_script}'", check=False):
                print("  Warning: Backup may have issues, continuing anyway...")
        else:
            print("  Warning: Backup script not found, skipping...")
    else:
        print("\n[1/5] Backup skipped (--no-backup)")

    # Step 2: Pull latest changes
    print("\n[2/5] Pulling latest changes from upstream...")
    if not run("git fetch upstream 2>/dev/null || git fetch origin"):
        print("  Failed to fetch updates", file=sys.stderr)
        sys.exit(1)

    current_branch = subprocess.run(
        "git branch --show-current", shell=True, capture_output=True, text=True
    ).stdout.strip() or "main"

    # Try merging upstream, fall back to origin
    if not run(f"git merge upstream/{current_branch} --no-edit 2>/dev/null", check=False):
        if not run(f"git pull origin {current_branch} --no-edit", check=False):
            print("  Warning: Could not merge upstream changes. Continuing with current code...")

    # Step 3: Rebuild Docker image
    print("\n[3/5] Rebuilding Docker image...")
    if not run("docker compose build", timeout=600):
        print("  Failed to build image", file=sys.stderr)
        sys.exit(1)

    # Step 4: Restart services
    print("\n[4/5] Restarting services...")
    if not run("docker compose down && docker compose up -d openclaw-gateway"):
        print("  Failed to restart services", file=sys.stderr)
        sys.exit(1)

    # Step 5: Health check
    print("\n[5/5] Running health check...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        result = subprocess.run(
            f"python3 '{health_script}' --wait", shell=True, timeout=120
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
