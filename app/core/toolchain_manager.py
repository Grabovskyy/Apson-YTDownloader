from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.paths import AppPaths


@dataclass(frozen=True, slots=True)
class ToolchainPaths:
    ffmpeg: Path
    ffprobe: Path
    deno: Path


class ToolchainError(RuntimeError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ToolchainManager:
    """Resolve bundled tools explicitly; never fall back to the system PATH."""

    WINDOWS_X64_MACHINE = 0x8664

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    @property
    def platform_dir(self) -> Path:
        if sys.platform == "win32":
            return self.paths.bin_dir / "windows-x64"
        raise ToolchainError(
            "Bundlowany toolchain jest obecnie przygotowany wyłącznie dla Windows x64."
        )

    def resolve(self, *, validate: bool = True) -> ToolchainPaths:
        directory = self.platform_dir
        toolchain = ToolchainPaths(
            ffmpeg=directory / "ffmpeg.exe",
            ffprobe=directory / "ffprobe.exe",
            deno=directory / "deno.exe",
        )
        missing = [
            path.name
            for path in (toolchain.ffmpeg, toolchain.ffprobe, toolchain.deno)
            if not path.is_file()
        ]
        if missing:
            raise ToolchainError(
                "Brakuje bundlowanych narzędzi: "
                + ", ".join(missing)
                + f". Oczekiwany katalog: {directory}"
            )
        if validate:
            self._validate(toolchain)
        return toolchain

    def _validate(self, toolchain: ToolchainPaths) -> None:
        for executable in (toolchain.ffmpeg, toolchain.ffprobe, toolchain.deno):
            if not self.is_windows_x64_executable(executable):
                raise ToolchainError(
                    f"Narzędzie {executable.name} nie jest prawidłową binarką Windows x64."
                )

        checks = (
            (toolchain.ffmpeg, "-version"),
            (toolchain.ffprobe, "-version"),
            (toolchain.deno, "--version"),
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for executable, version_argument in checks:
            try:
                result = subprocess.run(
                    [str(executable), version_argument],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                    creationflags=creation_flags,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise ToolchainError(
                    f"Nie można uruchomić {executable.name}: {error}"
                ) from error
            if result.returncode != 0:
                raise ToolchainError(
                    f"Narzędzie {executable.name} zwróciło kod {result.returncode}."
                )

    @classmethod
    def is_windows_x64_executable(cls, path: Path) -> bool:
        try:
            with path.open("rb") as executable:
                if executable.read(2) != b"MZ":
                    return False
                executable.seek(0x3C)
                pe_offset = struct.unpack("<I", executable.read(4))[0]
                executable.seek(pe_offset)
                if executable.read(4) != b"PE\0\0":
                    return False
                machine = struct.unpack("<H", executable.read(2))[0]
                return machine == cls.WINDOWS_X64_MACHINE
        except (OSError, struct.error):
            return False


def load_tools_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("tools"), list):
        raise ValueError("Nieobsługiwany format manifestu narzędzi.")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise ValueError(
            f"Nieprawidłowa suma SHA-256 pliku {path.name}: oczekiwano {expected}, otrzymano {actual}."
        )
