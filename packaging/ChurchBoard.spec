# Build from the project root with:
#   pyinstaller packaging/ChurchBoard.spec --noconfirm --clean
from pathlib import Path
import sys


project = Path.cwd()
if not (project / "run.py").is_file():
    project = Path(SPECPATH).resolve().parent

version_scope = {}
exec((project / "app" / "version.py").read_text(), version_scope)
app_version = version_scope["__version__"]

a = Analysis(
    [str(project / "run.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(project / "app" / "static"), "app/static")],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="ChurchBoard",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
    )
    collected = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name="ChurchBoard",
    )
    app = BUNDLE(
        collected,
        name="ChurchBoard.app",
        bundle_identifier="org.churchboard.app",
        info_plist={
            "CFBundleDisplayName": "ChurchBoard",
            "CFBundleName": "ChurchBoard",
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="ChurchBoard",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=sys.platform != "win32",
    )
