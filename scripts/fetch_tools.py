from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.toolchain_manager import load_tools_manifest, verify_sha256


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if destination_root not in target.parents and target != destination_root:
                raise ValueError(f"Niebezpieczna ścieżka w archiwum: {member.filename}")
        zipped.extractall(destination)


def _find_file(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise FileNotFoundError(f"Oczekiwano dokładnie jednego pliku {name}, znaleziono {len(matches)}.")
    return matches[0]


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "YTDownloader-tool-fetcher",
        },
    )
    with urllib.request.urlopen(request) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def fetch_tools(manifest_path: Path, destination: Path, download_dir: Path) -> None:
    manifest = load_tools_manifest(manifest_path)
    destination.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    for tool in manifest["tools"]:
        archive = download_dir / f"{tool['name']}-{tool['version']}.zip"
        if not archive.exists():
            print(f"Pobieranie {tool['name']} {tool['version']}…")
            partial_archive = archive.with_suffix(".zip.part")
            _download(tool["url"], partial_archive)
            verify_sha256(partial_archive, tool["sha256"])
            partial_archive.replace(archive)
        verify_sha256(archive, tool["sha256"])

        extraction_dir = download_dir / f"extract-{tool['name']}"
        resolved_download_dir = download_dir.resolve()
        resolved_extraction_dir = extraction_dir.resolve()
        if resolved_download_dir not in resolved_extraction_dir.parents:
            raise ValueError(f"Katalog rozpakowania wychodzi poza katalog roboczy: {extraction_dir}")
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir)
        extraction_dir.mkdir(parents=True)
        _safe_extract(archive, extraction_dir)
        for executable_name in tool["executables"]:
            source = _find_file(extraction_dir, executable_name)
            shutil.copy2(source, destination / executable_name)
        if tool.get("archive_license") and tool.get("license_output"):
            license_source = _find_file(extraction_dir, tool["archive_license"])
            license_directory = destination / "licenses"
            license_directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(license_source, license_directory / tool["license_output"])
        shutil.rmtree(extraction_dir)

    print(f"Toolchain gotowy: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pobierz zweryfikowany toolchain YTDownloader.")
    parser.add_argument(
        "--manifest", type=Path, default=PROJECT_ROOT / "tools-manifest.json"
    )
    parser.add_argument(
        "--destination", type=Path, default=PROJECT_ROOT / "bin" / "windows-x64"
    )
    parser.add_argument(
        "--download-dir", type=Path, default=PROJECT_ROOT / "data" / "temp" / "toolchain"
    )
    arguments = parser.parse_args()
    fetch_tools(
        arguments.manifest.resolve(),
        arguments.destination.resolve(),
        arguments.download_dir.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
