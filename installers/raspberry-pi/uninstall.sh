#!/usr/bin/env bash
set -euo pipefail

sudo systemctl disable --now churchboard.service >/dev/null 2>&1 || true
sudo /bin/rm -f /etc/systemd/system/churchboard.service
sudo systemctl daemon-reload
/bin/rm -f "$HOME/.config/autostart/churchboard-kiosk.desktop"
/bin/rm -f "$HOME/.local/bin/churchboard-kiosk"
/bin/rm -rf "$HOME/.local/share/churchboard/app"

echo "ChurchBoard and its startup entries were removed."
echo "Settings remain in $HOME/.local/share/churchboard/data."
