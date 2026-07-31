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
.build-venv/bin/pyinstaller packaging/ChurchBoard.spec --noconfirm --clean

VERSION="$("$PYTHON_BIN" -c 'from app.version import __version__; print(__version__)')"
ARCH="$(uname -m)"
APP_PATH="$PROJECT_DIR/dist/ChurchBoard.app"
PKG_PATH="$PROJECT_DIR/dist/ChurchBoard-${VERSION}-macOS-${ARCH}.pkg"
DMG_PATH="$PROJECT_DIR/dist/ChurchBoard-${VERSION}-macOS-${ARCH}.dmg"

PACKAGE_STAGE="$(/usr/bin/mktemp -d /private/tmp/churchboard-package.XXXXXX)"
cleanup_package_stage() {
  /bin/rm -rf "$PACKAGE_STAGE"
}
trap cleanup_package_stage EXIT

STAGED_APP="$PACKAGE_STAGE/ChurchBoard.app"
COPYFILE_DISABLE=1 /bin/cp -R "$APP_PATH" "$STAGED_APP"
/usr/bin/xattr -cr "$STAGED_APP"
/usr/bin/find "$STAGED_APP" -name '._*' -delete
/usr/bin/codesign --force --deep --sign - "$STAGED_APP"
/usr/bin/xattr -cr "$STAGED_APP"
/usr/bin/find "$STAGED_APP" -name '._*' -delete
COPYFILE_DISABLE=1 /usr/bin/pkgbuild \
  --component "$STAGED_APP" \
  --install-location /Applications \
  --scripts "$PROJECT_DIR/installers/macos/pkg-scripts" \
  --identifier org.churchboard.app \
  --version "$VERSION" \
  "$PACKAGE_STAGE/ChurchBoard.pkg"

DMG_STAGE="$PACKAGE_STAGE/dmg"
/bin/mkdir -p "$DMG_STAGE"
COPYFILE_DISABLE=1 /bin/cp "$PACKAGE_STAGE/ChurchBoard.pkg" "$DMG_STAGE/ChurchBoard-${VERSION}-macOS-${ARCH}.pkg"
/bin/cp "$PROJECT_DIR/installers/macos/Uninstall ChurchBoard.command" "$DMG_STAGE/"
/usr/bin/hdiutil create -volname "ChurchBoard ${VERSION}" -srcfolder "$DMG_STAGE" -ov -format UDZO "$PACKAGE_STAGE/ChurchBoard.dmg"
COPYFILE_DISABLE=1 /bin/cp "$PACKAGE_STAGE/ChurchBoard.pkg" "$PKG_PATH"
COPYFILE_DISABLE=1 /bin/cp "$PACKAGE_STAGE/ChurchBoard.dmg" "$DMG_PATH"

echo "Built:"
echo "  $PKG_PATH"
echo "  $DMG_PATH"
