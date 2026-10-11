#!/usr/bin/env bash
# Run as ohmega AFTER `claude` is installed, logged in (/login), and `claude remote-control` was run once
# interactively in ~/Algent to accept the enable + trust prompts.
set -euo pipefail
mkdir -p ~/.config/systemd/user
cp "$(dirname "$0")/claude-rc.service" ~/.config/systemd/user/claude-rc.service
sudo loginctl enable-linger "$USER"          # user services run without anyone logged in
systemctl --user daemon-reload
systemctl --user enable --now claude-rc.service
systemctl --user --no-pager status claude-rc.service | head -n 5
