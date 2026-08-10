from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]

datas = [
    (str(PROJECT_ROOT / "assets"), "assets"),
    (str(PROJECT_ROOT / "bin" / "windows-x64"), "bin/windows-x64"),
    (str(PROJECT_ROOT / "THIRD_PARTY_LICENSES"), "THIRD_PARTY_LICENSES"),
    (str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(PROJECT_ROOT / "LICENSE"), "."),
    (str(PROJECT_ROOT / "BRANDING.md"), "."),
    (str(PROJECT_ROOT / "tools-manifest.json"), "."),
]
binaries = []
hiddenimports = []

for package in ("yt_dlp", "yt_dlp_ejs", "certifi"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for distribution in (
    "PySide6",
    "shiboken6",
    "yt-dlp",
    "yt-dlp-ejs",
    "requests",
    "certifi",
):
    datas += copy_metadata(distribution)

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ApsonYTDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    version=str(PROJECT_ROOT / "packaging" / "windows" / "version_info.txt"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    contents_directory=".",
    icon=str(PROJECT_ROOT / "assets" / "icons" / "apson-ytdownloader.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ApsonYTDownloader",
)
