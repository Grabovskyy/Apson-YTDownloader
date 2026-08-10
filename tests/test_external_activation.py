from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.core.external_activation import ExternalActivation, ExternalActivationError
from app.core.settings_manager import SettingsManager
from app.core.single_instance import SingleInstanceCoordinator
from app.main_window import MainWindow
from app.utils.paths import AppPaths
from tests.test_analysis_gui import DeferredThreadPool, FakeAnalyzer


class ExternalActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_protocol_and_command_line_parse_encoded_url(self) -> None:
        url = "https://www.youtube.com/watch?v=one&list=PL-test"
        uri = f"apson-ytdownloader://add?url={quote(url, safe='')}"
        activation = ExternalActivation.from_protocol_uri(uri)
        from_argv = ExternalActivation.from_argv(["app.exe", "--protocol", uri])

        self.assertEqual(activation.url, url)
        self.assertTrue(activation.auto_analyze)
        self.assertEqual(from_argv, activation)

    def test_rejects_unknown_actions_and_unsafe_urls(self) -> None:
        invalid = (
            "apson-ytdownloader://delete?url=https%3A%2F%2Fexample.test",
            "apson-ytdownloader://add?url=file%3A%2F%2F%2FC%3A%2Fsecret",
            "apson-ytdownloader://add?url=https%3A%2F%2Fuser%3Apass%40example.test",
        )
        for uri in invalid:
            with self.subTest(uri=uri), self.assertRaises(ExternalActivationError):
                ExternalActivation.from_protocol_uri(uri)

    def test_single_instance_forwards_url(self) -> None:
        name = f"Apson.YTDownloader.Tests.{uuid4().hex}"
        primary = SingleInstanceCoordinator(name)
        received = QSignalSpy(primary.activation_received)
        self.assertTrue(primary.listen())
        sender_code = """
import sys
from app.core.external_activation import ExternalActivation
from app.core.single_instance import SingleInstanceCoordinator
ok = SingleInstanceCoordinator(sys.argv[1]).forward_to_running(
    ExternalActivation("https://example.test/one"), 3000
)
raise SystemExit(0 if ok else 1)
"""
        sender = subprocess.Popen(
            [sys.executable, "-c", sender_code, name],
            cwd=Path.cwd(),
        )
        deadline = time.monotonic() + 3
        while sender.poll() is None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        sender.wait(timeout=1)
        self.app.processEvents()
        self.assertEqual(sender.returncode, 0)
        self.assertEqual(received.count(), 1)
        self.assertEqual(received.at(0)[0].url, "https://example.test/one")
        primary.close()

    def test_external_urls_queue_during_active_analysis_and_deduplicate(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=Path(temporary) / "data")
            paths.ensure_directories()
            pool = DeferredThreadPool()
            window = MainWindow(
                paths,
                SettingsManager(paths),
                analyzer=FakeAnalyzer(),  # type: ignore[arg-type]
                thread_pool=pool,  # type: ignore[arg-type]
            )
            first = ExternalActivation("https://example.test/one")
            second = ExternalActivation("https://example.test/two")
            window.handle_external_activation(first)
            first_worker = pool.worker
            window.handle_external_activation(second)
            window.handle_external_activation(second)
            self.assertEqual(window._pending_external_urls, [second.url])

            first_worker.run()  # type: ignore[union-attr]
            self.app.processEvents()
            second_worker = pool.worker
            self.assertIsNot(second_worker, first_worker)
            second_worker.run()  # type: ignore[union-attr]

            self.assertEqual(len(window.queue.items), 2)
            self.assertEqual(window._pending_external_urls, [])
            window.close()

    def test_app_config_redirects_data_but_portable_wins(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            app_dir = root / "app"
            configured = root / "configured-data"
            app_dir.mkdir()
            (app_dir / "app-config.json").write_text(
                json.dumps({"schema_version": 1, "data_dir": str(configured)}),
                encoding="utf-8",
            )
            self.assertEqual(
                AppPaths.discover(app_dir=app_dir, portable=False).data_dir,
                configured.resolve(),
            )
            (app_dir / ".portable").touch()
            self.assertEqual(
                AppPaths.discover(app_dir=app_dir).data_dir,
                (app_dir / "data").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
