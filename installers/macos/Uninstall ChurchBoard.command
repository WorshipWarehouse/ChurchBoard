#!/bin/zsh
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/org.churchboard.app.plist"
/bin/launchctl bootout "gui/$(/usr/bin/id -u)" "$PLIST" >/dev/null 2>&1 || true
/bin/rm -f "$PLIST"

if [[ -d "/Applications/ChurchBoard.app" ]]; then
  /usr/bin/osascript -e 'do shell script "/bin/rm -rf /Applications/ChurchBoard.app" with administrator privileges'
fi

echo "ChurchBoard was removed. Your settings remain in $HOME/.churchboard."
echo "Press Return to close."
read -r
