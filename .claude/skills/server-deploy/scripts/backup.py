#!/usr/bin/env python3
"""Backup OpenClaw data (config, memory, sessions)."""

import argparse
import datetime
import os
import subprocess
import sys

from common import get_config_dir, run


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

    paths_to_backup = [config_dir]

    workspace_dir = os.path.join(config_dir, "workspace")
    exclude_args = ""
    if not args.include_workspace and os.path.exists(workspace_dir):
        exclude_args = f"--exclude='{workspace_dir}'"

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

    run(cmd, check=False)

    if os.path.exists(archive_path):
        size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        print(f"\n  ✓ Backup created: {archive_path} ({size_mb:.1f} MB)")

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
