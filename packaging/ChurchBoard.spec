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
mac_icon = str(project / "packaging" / "assets" / "ChurchBoard.icns")
windows_icon = str(project / "packaging" / "assets" / "ChurchBoard.ico")
datas = [
    (str(project / "app" / "static"), "app/static"),
    (str(project / "LICENSE"), "."),
    (str(project / "LEGAL.md"), "."),
    (str(project / "THIRD_PARTY_NOTICES.md"), "."),
]
collected_licenses = project / "build" / "legal" / "third-party"
if collected_licenses.is_dir():
    datas.append((str(collected_licenses), "legal/third-party"))
tray_hidden_imports = []
if sys.platform == "darwin":
    tray_hidden_imports.extend(["app.tray", "PIL.Image", "pystray", "pystray._darwin"])
elif sys.platform == "win32":
    tray_hidden_imports.extend(["app.tray", "PIL.Image", "pystray", "pystray._win32"])

a = Analysis(
    [str(project / "run.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        *tray_hidden_imports,
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
        icon=mac_icon,
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
        icon=mac_icon,
        info_plist={
            "CFBundleDisplayName": "ChurchBoard",
            "CFBundleName": "ChurchBoard",
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
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
        icon=windows_icon if sys.platform == "win32" else None,
    )
