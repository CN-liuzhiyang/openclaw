#!/usr/bin/env python3
"""Rollback OpenClaw to a previous version (source and Docker modes)."""

import argparse
import os
import subprocess
import sys

from common import (
    detect_mode, detect_pm, run_verbose, run,
    stop_service, start_service, restart_service,
)


def list_backups(backup_dir):
    """List available backups."""
    if not os.path.exists(backup_dir):
        return []
    return sorted(
        [f for f in os.listdir(backup_dir)
         if f.startswith("openclaw_backup_") and f.endswith(".tar.gz")],
        reverse=True,
    )


def list_git_tags():
    """List recent git tags for source rollback."""
    output = run("git tag --sort=-creatordate 2>/dev/null")
    if output:
        return output.strip().split("\n")[:10]
    return []


def list_git_commits(n=10):
    """List recent git commits."""
    output = run(f"git log --oneline -n {n} 2>/dev/null")
    if output:
        return output.strip().split("\n")
    return []


def rollback_docker(backup_path):
    """Rollback Docker deployment from backup."""
    print("\n[1/4] Stopping services...")
    run_verbose("docker compose down")

    print("\n[2/4] Restoring data from backup...")
    if not run_verbose(f"tar xzf '{backup_path}' -C /"):
        print("  Failed to restore backup", file=sys.stderr)
        sys.exit(1)

    print("\n[3/4] Restarting services...")
    if not run_verbose("docker compose up -d openclaw-gateway"):
        print("  Failed to restart services", file=sys.stderr)
        sys.exit(1)

    print("\n[4/4] Running health check...")
    run_health_check("docker")


def rollback_source(target, pm):
    """Rollback source deployment to a git ref (tag or commit)."""
    print(f"\n[1/5] Stopping service...")
    stop_service("source", pm)

    print(f"\n[2/5] Stashing local changes...")
    run_verbose("git stash 2>/dev/null", check=False)

    print(f"\n[3/5] Checking out {target}...")
    if not run_verbose(f"git checkout {target}"):
        print(f"  Failed to checkout {target}", file=sys.stderr)
        sys.exit(1)

    print("\n[4/5] Rebuilding from source...")
    if not run_verbose("pnpm install --frozen-lockfile 2>/dev/null || pnpm install", timeout=300):
        print("  Failed to install dependencies", file=sys.stderr)
        sys.exit(1)
    if not run_verbose("pnpm build", timeout=600):
        print("  Failed to build", file=sys.stderr)
        sys.exit(1)

    print("\n[5/5] Starting service...")
    start_service("source", pm)
    run_health_check("source")


def rollback_source_from_backup(backup_path, pm):
    """Rollback source deployment from data backup."""
    print("\n[1/3] Stopping service...")
    stop_service("source", pm)

    print("\n[2/3] Restoring data from backup...")
    if not run_verbose(f"tar xzf '{backup_path}' -C /"):
        print("  Failed to restore backup", file=sys.stderr)
        sys.exit(1)

    print("\n[3/3] Starting service...")
    start_service("source", pm)
    run_health_check("source")


def run_health_check(mode):
    """Run health check script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        subprocess.run(
            f"python3 '{health_script}' --wait --mode {mode}",
            shell=True, timeout=120,
        )


def main():
    parser = argparse.ArgumentParser(description="Rollback OpenClaw")
    parser.add_argument("--mode", choices=["source", "docker"], default=None)
    parser.add_argument("--pm", choices=["systemd", "pm2"], default=None)
    parser.add_argument("--backup-dir", default=os.path.expanduser("~/openclaw-backups"))
    parser.add_argument("--backup-file", help="Specific backup file to restore")
    parser.add_argument("--git-ref", help="Git tag or commit to rollback to (source mode)")
    parser.add_argument("--list", action="store_true", help="List available rollback targets")
    args = parser.parse_args()

    mode = detect_mode(args.mode)
    pm = detect_pm(args.pm)
    backups = list_backups(args.backup_dir)

    if args.list:
        print("\n  Available Backups:")
        if backups:
            for i, b in enumerate(backups):
                bpath = os.path.join(args.backup_dir, b)
                bsize = os.path.getsize(bpath) / (1024 * 1024)
                print(f"  [{i}] {b} ({bsize:.1f} MB)")
        else:
            print("  No backups found.")

        if mode == "source":
            tags = list_git_tags()
            if tags:
                print("\n  Available Git Tags:")
                for t in tags:
                    print(f"    {t}")
            commits = list_git_commits()
            if commits:
                print("\n  Recent Git Commits:")
                for c in commits:
                    print(f"    {c}")
        sys.exit(0)

    print("\n" + "=" * 60)
    print(f"  OpenClaw Rollback (mode: {mode})")
    print("=" * 60)

    # Determine rollback strategy
    if args.git_ref and mode == "source":
        # Git-based rollback (source only)
        print(f"\n  Rolling back to git ref: {args.git_ref}")
        rollback_source(args.git_ref, pm)
    elif args.backup_file or backups:
        # Backup-based rollback
        if args.backup_file:
            backup_path = args.backup_file
            if not os.path.isabs(backup_path):
                backup_path = os.path.join(args.backup_dir, backup_path)
        else:
            backup_path = os.path.join(args.backup_dir, backups[0])

        if not os.path.exists(backup_path):
            print(f"  Backup not found: {backup_path}", file=sys.stderr)
            sys.exit(1)

        backup_name = os.path.basename(backup_path)
        backup_size = os.path.getsize(backup_path) / (1024 * 1024)
        print(f"\n  Restoring from: {backup_name} ({backup_size:.1f} MB)")

        if mode == "docker":
            rollback_docker(backup_path)
        else:
            rollback_source_from_backup(backup_path, pm)
    else:
        print("  No rollback target specified.", file=sys.stderr)
        print("  Use --git-ref <tag/commit> or --backup-file <path>", file=sys.stderr)
        print("  Use --list to see available targets.", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  ✓ Rollback completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
