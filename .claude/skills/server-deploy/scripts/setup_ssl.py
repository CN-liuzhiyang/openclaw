#!/usr/bin/env python3
"""Configure Let's Encrypt SSL for OpenClaw via Nginx."""

import argparse
import subprocess
import sys


def run(cmd, timeout=120, check=True):
    """Run a shell command."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        print(f"    {result.stdout.strip()[:300]}")
    if check and result.returncode != 0:
        if result.stderr.strip():
            print(f"    Error: {result.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Setup SSL for OpenClaw")
    parser.add_argument("--domain", required=True, help="Domain name")
    parser.add_argument("--email", help="Email for Let's Encrypt notifications")
    args = parser.parse_args()

    if not args.email:
        print("  Note: No email provided. Using --register-unsafely-without-email")

    print("\n" + "=" * 60)
    print("  SSL Setup for OpenClaw")
    print("=" * 60)
    print(f"  Domain: {args.domain}")

    # Step 1: Install certbot
    print("\n[1/3] Installing certbot...")
    result = subprocess.run("certbot --version", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        if not run("apt update && apt install -y certbot python3-certbot-nginx"):
            print("  Failed to install certbot", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"  Certbot already installed: {result.stdout.strip() or result.stderr.strip()}")

    # Step 2: Obtain certificate
    print("\n[2/3] Obtaining SSL certificate...")
    email_arg = f"-m {args.email}" if args.email else "--register-unsafely-without-email"
    cmd = f"certbot --nginx -d {args.domain} {email_arg} --non-interactive --agree-tos"
    if not run(cmd, timeout=180):
        print("  Failed to obtain SSL certificate", file=sys.stderr)
        print("  Make sure:")
        print("    1. Domain DNS is pointing to this server")
        print("    2. Port 80 is accessible from the internet")
        print("    3. Nginx is running")
        sys.exit(1)

    # Step 3: Verify and set up auto-renewal
    print("\n[3/3] Setting up auto-renewal...")
    run("certbot renew --dry-run", check=False)

    # Check if systemd timer exists
    timer_check = subprocess.run(
        "systemctl is-active certbot.timer", shell=True, capture_output=True, text=True
    )
    if timer_check.returncode == 0:
        print("  Auto-renewal timer is active")
    else:
        print("  Setting up cron-based renewal...")
        run("(crontab -l 2>/dev/null; echo '0 3 * * * certbot renew --quiet') | sort -u | crontab -", check=False)

    print("\n" + "=" * 60)
    print(f"  ✓ SSL configured! Access OpenClaw at https://{args.domain}")
    print("=" * 60)


if __name__ == "__main__":
    main()
