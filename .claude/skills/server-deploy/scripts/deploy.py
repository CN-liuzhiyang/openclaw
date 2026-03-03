#!/usr/bin/env python3
"""Deploy OpenClaw using docker-setup.sh or manual docker compose."""

import os
import subprocess
import sys


def run(cmd, timeout=600, check=True, interactive=False):
    """Run a shell command."""
    print(f"  $ {cmd}")
    if interactive:
        # For interactive commands, don't capture output
        result = subprocess.run(cmd, shell=True, timeout=timeout)
        return result.returncode == 0
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[-20:]:
            print(f"    {line}")
    if check and result.returncode != 0:
        if result.stderr.strip():
            for line in result.stderr.strip().split("\n")[-10:]:
                print(f"    Error: {line}", file=sys.stderr)
        return False
    return True


def setup_env():
    """Ensure .env file exists with required values."""
    if os.path.exists(".env"):
        print("  .env file already exists")
        return True

    if not os.path.exists(".env.example"):
        print("  Warning: .env.example not found", file=sys.stderr)
        return False

    # Copy .env.example to .env
    with open(".env.example") as f:
        content = f.read()

    with open(".env", "w") as f:
        f.write(content)

    print("  Created .env from .env.example")
    print("  ⚠ You need to configure API keys in .env before deploying!")
    return True


def deploy_with_script():
    """Deploy using the official docker-setup.sh."""
    if not os.path.exists("docker-setup.sh"):
        return False

    print("  Using official docker-setup.sh...")
    run("chmod +x docker-setup.sh", check=False)
    return run("./docker-setup.sh", timeout=900, interactive=True)


def deploy_manual():
    """Deploy manually with docker compose."""
    print("  Using manual docker compose deployment...")

    # Build image
    print("\n  Building Docker image...")
    if not run("docker compose build", timeout=900):
        return False

    # Start gateway
    print("\n  Starting OpenClaw gateway...")
    if not run("docker compose up -d openclaw-gateway"):
        return False

    return True


def main():
    use_script = "--use-script" in sys.argv
    manual = "--manual" in sys.argv

    print("\n" + "=" * 60)
    print("  OpenClaw Deployment")
    print("=" * 60)

    # Check we're in the right directory
    if not os.path.exists("docker-compose.yml"):
        print("  Error: docker-compose.yml not found.", file=sys.stderr)
        print("  Make sure you're in the OpenClaw project directory.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Setup .env
    print("\n[1/3] Checking environment configuration...")
    setup_env()

    # Step 2: Deploy
    print("\n[2/3] Deploying OpenClaw...")
    if manual or not os.path.exists("docker-setup.sh"):
        success = deploy_manual()
    else:
        success = deploy_with_script()
        if not success:
            print("  docker-setup.sh failed, falling back to manual deployment...")
            success = deploy_manual()

    if not success:
        print("\n  ✗ Deployment failed!", file=sys.stderr)
        sys.exit(1)

    # Step 3: Health check
    print("\n[3/3] Running health check...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    health_script = os.path.join(script_dir, "health_check.py")
    if os.path.exists(health_script):
        subprocess.run(f"python3 '{health_script}' --wait", shell=True, timeout=120)

    print("\n" + "=" * 60)
    print("  ✓ OpenClaw deployed successfully!")
    print("  Access the web UI at http://<server-ip>:18789")
    print("=" * 60)


if __name__ == "__main__":
    main()
