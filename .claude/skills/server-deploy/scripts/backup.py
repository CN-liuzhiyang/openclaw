#!/usr/bin/env python3
"""Backup OpenClaw data (config, memory, sessions)."""

import argparse
import datetime
import os
import subprocess
import sys


def run(cmd, check=True):
    """Run a shell command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return None
    return result.stdout.strip()


def get_config_dir():
    """Get OpenClaw config directory from .env or default."""
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENCLAW_CONFIG_DIR="):
                    path = line.split("=", 1)[1].strip('"').strip("'")
                    return os.path.expanduser(path)
    return os.path.expanduser("~/.openclaw")


def main():
    parser = argparse.ArgumentParser(description="Backup OpenClaw data")
    parser.add_argument("--output-dir", default=os.path.expanduser("~/openclaw-backups"),
                        help="Backup output directory")
    parser.add_argument("--config-dir", default=None,
                        help="OpenClaw config directory (auto-detected from .env)")
    parser.add_argument("--include-workspace", action="store_true",
                        help="Also backup workspace files (can be large)")
    args = parser.parse_args()

    config_dir = args.config_dir or get_config_dir()
    backup_dir = args.output_dir

    if not os.path.exists(config_dir):
        print(f"Error: Config directory not found: {config_dir}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"openclaw_backup_{timestamp}.tar.gz"
    archive_path = os.path.join(backup_dir, archive_name)

    # Determine what to backup
    paths_to_backup = [config_dir]

    # Exclude workspace by default (can be very large)
    workspace_dir = os.path.join(config_dir, "workspace")
    exclude_args = ""
    if not args.include_workspace and os.path.exists(workspace_dir):
        exclude_args = f"--exclude='{workspace_dir}'"

    # Also backup .env file if it exists
    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_file):
        paths_to_backup.append(env_file)

    paths_str = " ".join(f"'{p}'" for p in paths_to_backup)
    cmd = f"tar czf '{archive_path}' {exclude_args} {paths_str} 2>/dev/null"

    print(f"Creating backup...")
    print(f"  Source: {config_dir}")
    print(f"  Target: {archive_path}")
    if not args.include_workspace:
        print(f"  Note: Workspace excluded (use --include-workspace to include)")

    result = run(cmd, check=False)

    if os.path.exists(archive_path):
        size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        print(f"\n  ✓ Backup created: {archive_path} ({size_mb:.1f} MB)")

        # List existing backups
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith("openclaw_backup_")],
            reverse=True,
        )
        print(f"\n  Total backups: {len(backups)}")
        for b in backups[:5]:
            bpath = os.path.join(backup_dir, b)
            bsize = os.path.getsize(bpath) / (1024 * 1024)
            print(f"    - {b} ({bsize:.1f} MB)")
        if len(backups) > 5:
            print(f"    ... and {len(backups) - 5} more")
    else:
        print("  ✗ Backup failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
