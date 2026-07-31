#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now churchboard.service >/dev/null 2>&1 || true
/bin/rm -f "$HOME/.config/systemd/user/churchboard.service"
/bin/rm -f "$HOME/.local/share/applications/churchboard.desktop"
/bin/rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/churchboard.png"
/bin/rm -f "$HOME/.local/share/churchboard/ChurchBoard"
systemctl --user daemon-reload

echo "ChurchBoard was removed. Settings remain in $HOME/.local/share/churchboard/data."
