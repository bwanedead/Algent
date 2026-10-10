#!/usr/bin/env bash
# Install the subscription-funded chart harnesses on the worker server (run as `ohmega`; uses sudo for Node).
#
#   grok-build  official x.ai installer (default analytics harness)   -> ~/.grok/bin/grok
#   codex       @openai/codex from npm, on Node 22 (fallback harness)  -> /usr/bin/codex
#
# Versions follow the laptop's so analytics behave the same. Logging in is interactive and done by the operator
# once per machine (device-code flow, approved in their browser):
#   grok login --device-auth
#   codex login --device-auth
set -euo pipefail
CODEX_VERSION="${CODEX_VERSION:-0.145.0}"

if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 22 ]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null
    sudo apt-get install -y nodejs >/dev/null
fi
sudo npm install -g --silent "@openai/codex@${CODEX_VERSION}"

[ -x "$HOME/.grok/bin/grok" ] || curl -fsSL https://x.ai/cli/install.sh | bash
grep -q '.grok/bin' "$HOME/.profile" || echo 'export PATH="$HOME/.grok/bin:$PATH"' >> "$HOME/.profile"

echo "node $(node -v) | $(codex --version) | $("$HOME/.grok/bin/grok" --version)"
