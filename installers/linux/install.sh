#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_BINARY="$SCRIPT_DIR/ChurchBoard"
if [[ ! -x "$SOURCE_BINARY" ]]; then
  echo "ChurchBoard was not found beside this installer." >&2
  exit 1
fi

INSTALL_DIR="$HOME/.local/share/churchboard"
SERVICE_DIR="$HOME/.config/systemd/user"
APPLICATION_DIR="$HOME/.local/share/applications"
/bin/mkdir -p "$INSTALL_DIR" "$SERVICE_DIR" "$APPLICATION_DIR"
/usr/bin/install -m 0755 "$SOURCE_BINARY" "$INSTALL_DIR/ChurchBoard"

/bin/cat > "$SERVICE_DIR/churchboard.service" <<EOF
[Unit]
Description=ChurchBoard production dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/ChurchBoard --background
Restart=always
RestartSec=3
Environment=CHURCHBOARD_HOST=0.0.0.0
Environment=CHURCHBOARD_DATA_DIR=$INSTALL_DIR/data

[Install]
WantedBy=default.target
EOF

/bin/cat > "$APPLICATION_DIR/churchboard.desktop" <<EOF
[Desktop Entry]
Name=ChurchBoard
Comment=Open ChurchBoard Setup
Exec=xdg-open http://127.0.0.1:8040/admin
Terminal=false
Type=Application
Categories=AudioVideo;Utility;
EOF

systemctl --user daemon-reload
systemctl --user enable --now churchboard.service
if command -v loginctl >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
  sudo loginctl enable-linger "$USER" >/dev/null 2>&1 || true
fi

echo "ChurchBoard is installed and will start automatically."
echo "Open http://127.0.0.1:8040/admin"
