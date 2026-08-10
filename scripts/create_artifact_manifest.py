from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Użycie: create_artifact_manifest.py <katalog> <wersja>")
    root = Path(sys.argv[1]).resolve()
    version = sys.argv[2]
    files = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name == "artifacts-manifest.json":
            continue
        files.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    payload = {
        "schema_version": 1,
        "application": "Apson YTDownloader",
        "version": version,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "runtime_packages": {
            name: importlib.metadata.version(name)
            for name in (
                "PySide6",
                "shiboken6",
                "yt-dlp",
                "yt-dlp-ejs",
                "requests",
                "certifi",
                "urllib3",
                "websockets",
                "mutagen",
                "brotli",
                "pycryptodomex",
            )
        },
        "artifacts": files,
    }
    target = root / "artifacts-manifest.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
