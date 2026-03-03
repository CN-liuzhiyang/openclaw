#!/usr/bin/env python3
"""Configure Nginx reverse proxy for OpenClaw."""

import argparse
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "templates")


def run(cmd, timeout=60, check=True):
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


def install_nginx():
    """Install Nginx if not already installed."""
    result = subprocess.run("nginx -v", shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  Nginx already installed: {result.stderr.strip()}")
        return True

    print("  Installing Nginx...")
    if not run("apt update && apt install -y nginx"):
        return False
    if not run("systemctl enable nginx"):
        return False
    return True


def generate_config(domain=None, gateway_port=18789):
    """Generate Nginx config from template."""
    template_path = os.path.join(TEMPLATE_DIR, "nginx-openclaw.conf")
    if not os.path.exists(template_path):
        print(f"  Template not found: {template_path}", file=sys.stderr)
        return None

    with open(template_path) as f:
        config = f.read()

    server_name = domain if domain else "_"
    config = config.replace("{{SERVER_NAME}}", server_name)
    config = config.replace("{{GATEWAY_PORT}}", str(gateway_port))

    return config


def main():
    parser = argparse.ArgumentParser(description="Setup Nginx reverse proxy for OpenClaw")
    parser.add_argument("--domain", help="Domain name (optional, defaults to server IP)")
    parser.add_argument("--port", type=int, default=18789, help="Gateway port (default: 18789)")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  Nginx Setup for OpenClaw")
    print("=" * 60)

    # Step 1: Install Nginx
    print("\n[1/4] Checking Nginx...")
    if not install_nginx():
        print("  Failed to install Nginx", file=sys.stderr)
        sys.exit(1)

    # Step 2: Generate config
    print("\n[2/4] Generating configuration...")
    config = generate_config(domain=args.domain, gateway_port=args.port)
    if not config:
        sys.exit(1)

    config_path = "/etc/nginx/sites-available/openclaw"
    with open(config_path, "w") as f:
        f.write(config)
    print(f"  Config written to {config_path}")

    # Step 3: Enable site
    print("\n[3/4] Enabling site...")
    # Remove default site if it exists
    default_link = "/etc/nginx/sites-enabled/default"
    if os.path.exists(default_link):
        os.remove(default_link)
        print("  Removed default site")

    enabled_link = "/etc/nginx/sites-enabled/openclaw"
    if os.path.exists(enabled_link):
        os.remove(enabled_link)
    os.symlink(config_path, enabled_link)
    print(f"  Enabled: {enabled_link}")

    # Step 4: Test and reload
    print("\n[4/4] Testing and reloading...")
    if not run("nginx -t"):
        print("  Nginx config test failed!", file=sys.stderr)
        sys.exit(1)

    if not run("systemctl reload nginx"):
        print("  Failed to reload Nginx", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    server_name = args.domain or "<server-ip>"
    print(f"  ✓ Nginx configured! Access OpenClaw at http://{server_name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
