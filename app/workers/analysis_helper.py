from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.core.toolchain_manager import ToolchainPaths
from app.services.media_analyzer import (
    AnalysisOptions,
    MediaAnalysisError,
    MediaAnalyzer,
    analysis_result_to_dict,
)
from app.utils.logging_config import configure_logging
from app.utils.paths import AppPaths
from app.utils.runtime_environment import configure_runtime_environment


def _paths_from_payload(data: dict[str, Any]) -> AppPaths:
    fields = {
        name: Path(str(data[name]))
        for name in (
            "app_dir",
            "data_dir",
            "settings_dir",
            "cache_dir",
            "history_dir",
            "thumbnails_dir",
            "temp_dir",
            "logs_dir",
            "downloads_dir",
        )
    }
    return AppPaths(**fields)


def _toolchain_from_payload(data: object) -> ToolchainPaths | None:
    if not isinstance(data, dict):
        return None
    return ToolchainPaths(
        ffmpeg=Path(str(data["ffmpeg"])),
        ffprobe=Path(str(data["ffprobe"])),
        deno=Path(str(data["deno"])),
    )


def run_request(payload: dict[str, Any]) -> dict[str, Any]:
    paths = _paths_from_payload(dict(payload["paths"]))
    paths.ensure_directories()
    configure_runtime_environment(paths)
    configure_logging(paths, "analysis-helper.log")
    options_data = dict(payload.get("options") or {})
    options = AnalysisOptions(
        video_playlist_behavior=str(options_data.get("video_playlist_behavior")),
        playlist_item_limit=int(options_data.get("playlist_item_limit", 100)),
    )
    analyzer = MediaAnalyzer(
        paths.cache_dir / "yt-dlp",
        toolchain=_toolchain_from_payload(payload.get("toolchain")),
    )
    try:
        result = analyzer.analyze_url(str(payload["url"]), options)
    except MediaAnalysisError as error:
        return {"ok": False, "message": error.user_message}
    return {"ok": True, "result": analysis_result_to_dict(result)}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Nieprawidłowe żądanie analizy.")
        response = run_request(payload)
    except Exception:
        response = {
            "ok": False,
            "message": "Proces analizy zakończył się nieoczekiwanym błędem. Szczegóły zapisano w logu.",
        }
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.flush()
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
