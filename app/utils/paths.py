from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass, replace
from pathlib import Path


DATA_DIR_ENV = "YTDOWNLOADER_DATA_DIR"
PORTABLE_ENV = "YTDOWNLOADER_PORTABLE"
APP_CONFIG_NAME = "app-config.json"


def _environment_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else None


def _application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _platform_data_directory(application_name: str) -> Path:
    """Return an OS-standard user data location without assuming a drive letter."""
    if sys.platform == "win32":
        root = _environment_path("LOCALAPPDATA") or _environment_path("APPDATA")
        if root is not None:
            return root / application_name
        return Path.home() / "AppData" / "Local" / application_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / application_name

    xdg_root = _environment_path("XDG_DATA_HOME")
    return (xdg_root if xdg_root is not None else Path.home() / ".local" / "share") / application_name


def _configured_data_directory(app_dir: Path) -> Path | None:
    config_file = app_dir / APP_CONFIG_NAME
    if not config_file.is_file():
        return None
    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
        configured = str(payload.get("data_dir") or "").strip()
    except (OSError, AttributeError, TypeError, json.JSONDecodeError):
        return None
    if not configured:
        return None
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else app_dir / path).resolve()


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Single source of truth for install and writable data locations.

    ``app_dir`` may be read-only after installation. Every writable category is
    independently represented and can be redirected by the installer/bootstrap,
    environment, or a future settings screen.
    """

    app_dir: Path
    data_dir: Path
    settings_dir: Path
    cache_dir: Path
    history_dir: Path
    thumbnails_dir: Path
    temp_dir: Path
    logs_dir: Path
    downloads_dir: Path

    @classmethod
    def discover(
        cls,
        *,
        app_dir: Path | None = None,
        data_dir: Path | None = None,
        portable: bool | None = None,
    ) -> "AppPaths":
        resolved_app_dir = (app_dir or _application_directory()).resolve()
        explicit_data_dir = data_dir.resolve() if data_dir is not None else _environment_path(DATA_DIR_ENV)
        configured_data_dir = _configured_data_directory(resolved_app_dir)

        if portable is None:
            portable_flag = os.environ.get(PORTABLE_ENV, "").strip().lower()
            portable = portable_flag in {"1", "true", "yes", "on"} or (
                resolved_app_dir / ".portable"
            ).is_file()

        if explicit_data_dir is not None:
            resolved_data_dir = explicit_data_dir
        elif portable:
            resolved_data_dir = resolved_app_dir / "data"
        elif configured_data_dir is not None:
            resolved_data_dir = configured_data_dir
        elif not getattr(sys, "frozen", False):
            # Development keeps all generated files inside the project on its drive.
            resolved_data_dir = resolved_app_dir / "data"
        else:
            resolved_data_dir = _platform_data_directory("Apson YTDownloader")

        def category(env_name: str, fallback: str) -> Path:
            return _environment_path(env_name) or resolved_data_dir / fallback

        return cls(
            app_dir=resolved_app_dir,
            data_dir=resolved_data_dir,
            settings_dir=category("YTDOWNLOADER_SETTINGS_DIR", "settings"),
            cache_dir=category("YTDOWNLOADER_CACHE_DIR", "cache"),
            history_dir=category("YTDOWNLOADER_HISTORY_DIR", "history"),
            thumbnails_dir=category("YTDOWNLOADER_THUMBNAILS_DIR", "thumbnails"),
            temp_dir=category("YTDOWNLOADER_TEMP_DIR", "temp"),
            logs_dir=category("YTDOWNLOADER_LOGS_DIR", "logs"),
            downloads_dir=category("YTDOWNLOADER_DOWNLOADS_DIR", "downloads"),
        )

    @property
    def settings_file(self) -> Path:
        return self.settings_dir / "settings.json"

    @property
    def history_file(self) -> Path:
        return self.history_dir / "history.json"

    @property
    def bin_dir(self) -> Path:
        return self.app_dir / "bin"

    @property
    def assets_dir(self) -> Path:
        return self.app_dir / "assets"

    def with_overrides(self, **paths: Path) -> "AppPaths":
        """Return a copy with selected categories redirected by a future UI."""
        allowed = {
            "data_dir",
            "settings_dir",
            "cache_dir",
            "history_dir",
            "thumbnails_dir",
            "temp_dir",
            "logs_dir",
            "downloads_dir",
        }
        unknown = set(paths) - allowed
        if unknown:
            raise ValueError(f"Nieznane kategorie ścieżek: {', '.join(sorted(unknown))}")
        return replace(self, **{key: Path(value).expanduser().resolve() for key, value in paths.items()})

    def ensure_directories(self) -> None:
        for directory in {
            self.data_dir,
            self.settings_dir,
            self.cache_dir,
            self.history_dir,
            self.thumbnails_dir,
            self.temp_dir,
            self.logs_dir,
            self.downloads_dir,
        }:
            directory.mkdir(parents=True, exist_ok=True)
