from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from app import __version__
from app.core.toolchain_manager import ToolchainError, ToolchainManager
from app.utils.paths import AppPaths
from app.utils.runtime_environment import configure_runtime_environment


def run_self_test(report_path: Path | None = None) -> int:
    paths = AppPaths.discover()
    paths.ensure_directories()
    configure_runtime_environment(paths)
    checks: dict[str, object] = {}
    failures: list[str] = []

    required_assets = (
        paths.assets_dir / "branding" / "piratecat.png",
        paths.assets_dir / "icons" / "apson-ytdownloader.ico",
        paths.assets_dir / "browser" / "install-button.html",
    )
    missing_assets = [str(path) for path in required_assets if not path.is_file()]
    checks["assets"] = {"ok": not missing_assets, "missing": missing_assets}
    if missing_assets:
        failures.append("assets")

    try:
        toolchain = ToolchainManager(paths).resolve(validate=True)
        checks["toolchain"] = {
            "ok": True,
            "ffmpeg": str(toolchain.ffmpeg),
            "ffprobe": str(toolchain.ffprobe),
            "deno": str(toolchain.deno),
        }
    except ToolchainError as error:
        checks["toolchain"] = {"ok": False, "error": error.user_message}
        failures.append("toolchain")

    checks["runtime_environment"] = {
        "ok": all(
            Path(os.environ[name]).resolve().drive == paths.data_dir.resolve().drive
            for name in ("TEMP", "TMP", "DENO_DIR")
        ),
        "TEMP": os.environ.get("TEMP"),
        "TMP": os.environ.get("TMP"),
        "DENO_DIR": os.environ.get("DENO_DIR"),
    }
    if not checks["runtime_environment"]["ok"]:  # type: ignore[index]
        failures.append("runtime_environment")

    payload = {
        "application": "Apson YTDownloader",
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version,
        "executable": sys.executable,
        "app_dir": str(paths.app_dir),
        "data_dir": str(paths.data_dir),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ok": not failures,
        "failures": failures,
        "checks": checks,
    }
    target = report_path or paths.logs_dir / "self-test.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    if sys.stdout is not None:
        print(json.dumps(payload, ensure_ascii=False))
    return 0 if not failures else 1
