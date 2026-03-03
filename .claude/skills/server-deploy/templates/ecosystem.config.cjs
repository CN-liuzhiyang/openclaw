// PM2 Ecosystem Configuration for OpenClaw Gateway
// Copy to project root and adjust paths as needed.

module.exports = {
  apps: [
    {
      name: "openclaw-gateway",
      script: "dist/index.js",
      args: "gateway --bind lan --port 18789",
      cwd: "{{PROJECT_DIR}}",
      interpreter: "node",
      env: {
        NODE_ENV: "production",
        OPENCLAW_CONFIG_DIR: "{{CONFIG_DIR}}",
        OPENCLAW_WORKSPACE_DIR: "{{WORKSPACE_DIR}}",
      },
      // Auto-restart
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      // Logging
      error_file: "{{CONFIG_DIR}}/logs/pm2-error.log",
      out_file: "{{CONFIG_DIR}}/logs/pm2-out.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      // Performance
      node_args: "--max-old-space-size=512",
      kill_timeout: 30000,
    },
  ],
};
