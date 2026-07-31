#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

find_python() {
  if [[ -n "${PYTHON:-}" ]] && "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "$PYTHON"
    return
  fi
  for candidate in "$PROJECT_DIR/.venv/bin/python" python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      command -v "$candidate"
      return
    fi
  done
  echo "Python 3.11 or newer is required to build ChurchBoard." >&2
  exit 1
}

PYTHON_BIN="$(find_python)"
"$PYTHON_BIN" -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/pip install -r requirements.txt -r build-requirements.txt
.build-venv/bin/python packaging/generate_brand_assets.py
.build-venv/bin/pyinstaller packaging/ChurchBoard.spec --noconfirm --clean

VERSION="$("$PYTHON_BIN" -c 'from app.version import __version__; print(__version__)')"
ARCH="$(uname -m)"
APP_PATH="$PROJECT_DIR/dist/ChurchBoard.app"
DMG_PATH="$PROJECT_DIR/dist/ChurchBoard-${VERSION}-macOS-${ARCH}.dmg"

PACKAGE_STAGE="$(/usr/bin/mktemp -d /private/tmp/churchboard-package.XXXXXX)"
cleanup_package_stage() {
  /bin/rm -rf "$PACKAGE_STAGE"
}
trap cleanup_package_stage EXIT

STAGED_APP="$PACKAGE_STAGE/ChurchBoard.app"
/usr/bin/ditto --norsrc --noextattr --noacl "$APP_PATH" "$STAGED_APP"
/usr/bin/xattr -cr "$STAGED_APP"
/usr/bin/find "$STAGED_APP" -name '._*' -delete
/usr/bin/codesign --force --deep --sign - "$STAGED_APP"
/usr/bin/xattr -cr "$STAGED_APP"
/usr/bin/find "$STAGED_APP" -name '._*' -delete

.build-venv/bin/dmgbuild \
  -s "$PROJECT_DIR/packaging/dmg-settings.py" \
  -D "app=$STAGED_APP" \
  -D "background=$PROJECT_DIR/packaging/assets/dmg-background.png" \
  -D "icon=$PROJECT_DIR/packaging/assets/ChurchBoard.icns" \
  "ChurchBoard ${VERSION}" "$PACKAGE_STAGE/ChurchBoard.dmg"
COPYFILE_DISABLE=1 /bin/cp "$PACKAGE_STAGE/ChurchBoard.dmg" "$DMG_PATH"

echo "Built:"
echo "  $DMG_PATH"
