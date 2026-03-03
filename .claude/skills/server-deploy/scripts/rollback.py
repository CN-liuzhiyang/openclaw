#!/usr/bin/env python3
"""Rollback OpenClaw to a previous version from backup."""

import argparse
import os
import subprocess
import sys


def run(cmd, timeout=120):
    """Run a shell command."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()[:200]}")
    if result.returncode != 0 and result.stderr.strip():
        print(f"    Error: {result.stderr.strip()[:200]}", file=sys.stderr)
    return result.returncode == 0


def list_backups(backup_dir):
    """List available backups."""
    if not os.path.exists(backup_dir):
        return []
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("openclaw_backup_") and f.endswith(".tar.gz")],
        reverse=True,
    )
    return backups


def main():
    parser = argparse.ArgumentParser(description="Rollback OpenClaw")
    parser.add_argument("--backup-dir", default=os.path.expanduser("~/openclaw-backups"))
    parser.add_argument("--backup-file", help="Specific backup file to restore")
    parser.add_argument("--list", action="store_true", help="List available backups")
    args = parser.parse_args()

    backups = list_backups(args.backup_dir)

    if args.list or (not args.backup_file and not backups):
        print("\n  Available Backups:")
        if not backups:
            print("  No backups found.")
            sys.exit(0)
        for i, b in enumerate(backups):
            bpath = os.path.join(args.backup_dir, b)
            bsize = os.path.getsize(bpath) / (1024 * 1024)
            print(f"  [{i}] {b} ({bsize:.1f} MB)")
        sys.exit(0)

    # Determine which backup to use
    if args.backup_file:
        backup_path = args.backup_file
        if not os.path.isabs(backup_path):
            backup_path = os.path.join(args.backup_dir, backup_path)
    else:
        if not backups:
            print("  No backups available. Cannot rollback.", file=sys.stderr)
            sys.exit(1)
        # Use most recent backup
        backup_path = os.path.join(args.backup_dir, backups[0])

    if not os.path.exists(backup_path):
        print(f"  Backup not found: {backup_path}", file=sys.stderr)
        sys.exit(1)

    backup_name = os.path.basename(backup_path)
    backup_size = os.path.getsize(backup_path) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("  OpenClaw Rollback")
    print("=" * 60)
    print(f"\n  Restoring from: {backup_name} ({backup_size:.1f} MB)")

    # Step 1: Stop services
    print("\n[1/4] Stopping services...")
    run("docker compose down")

    # Step 2: Restore data
    print("\n[2/4] Restoring data from backup...")
    if not run(f"tar xzf '{backup_path}' -C /"):
        print("  Failed to restore backup", file=sys.stderr)
        sys.exit(1)

    # Step 3: Restart services
    print("\n[3/4] Restarting services...")
    if not run("docker compose up -d openclaw-gateway"):
        print("  Failed to restart services", file=sys.stderr)
        sys.exit(1)

    # Step 4: Health check
    print("\n[4/4] Running health check...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        subprocess.run(f"python3 '{health_script}' --wait", shell=True, timeout=120)

    print("\n" + "=" * 60)
    print(f"  ✓ Rollback to {backup_name} completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
