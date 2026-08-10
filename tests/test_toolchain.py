from __future__ import annotations

import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.toolchain_manager import (
    ToolchainError,
    ToolchainManager,
    load_tools_manifest,
    sha256_file,
    verify_sha256,
)
from app.utils.paths import AppPaths
from app.utils.runtime_environment import configure_runtime_environment


def write_fake_pe(path: Path, machine: int = 0x8664) -> None:
    content = bytearray(128)
    content[:2] = b"MZ"
    content[0x3C:0x40] = struct.pack("<I", 64)
    content[64:68] = b"PE\0\0"
    content[68:70] = struct.pack("<H", machine)
    path.write_bytes(content)


class ToolchainTests(unittest.TestCase):
    def test_sha256_accepts_match_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            payload = Path(temporary) / "archive.zip"
            payload.write_bytes(b"verified payload")
            expected = sha256_file(payload)
            verify_sha256(payload, expected)
            with self.assertRaises(ValueError):
                verify_sha256(payload, "0" * 64)

    def test_manifest_has_pinned_tools(self) -> None:
        manifest = load_tools_manifest(Path.cwd() / "tools-manifest.json")
        tools = {tool["name"]: tool for tool in manifest["tools"]}
        self.assertEqual(tools["deno"]["version"], "2.8.1")
        self.assertEqual(len(tools["ffmpeg"]["sha256"]), 64)
        self.assertNotIn("latest", tools["deno"]["url"])
        self.assertNotIn("latest", tools["ffmpeg"]["url"])

    def test_resolve_does_not_fall_back_to_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            paths = AppPaths.discover(app_dir=Path(temporary), data_dir=Path(temporary) / "data")
            with self.assertRaises(ToolchainError) as caught:
                ToolchainManager(paths).resolve(validate=False)
            self.assertIn("Oczekiwany katalog", caught.exception.user_message)

    def test_x64_pe_detection(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            executable = Path(temporary) / "tool.exe"
            write_fake_pe(executable)
            self.assertTrue(ToolchainManager.is_windows_x64_executable(executable))
            write_fake_pe(executable, machine=0x014C)
            self.assertFalse(ToolchainManager.is_windows_x64_executable(executable))

    def test_runtime_environment_uses_app_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
            paths.ensure_directories()
            with patch.dict(os.environ, {}, clear=False):
                configure_runtime_environment(paths)
                self.assertEqual(os.environ["TEMP"], str(paths.temp_dir))
                self.assertEqual(os.environ["TMP"], str(paths.temp_dir))
                self.assertEqual(os.environ["DENO_DIR"], str(paths.cache_dir / "deno"))


if __name__ == "__main__":
    unittest.main()
