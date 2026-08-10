from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app import __version__
from app.core.settings_manager import SettingsManager
from app.main_window import MainWindow
from app.utils.paths import AppPaths


class BrandingAndReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_sidebar_branding_fits_without_clipping(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            paths = AppPaths.discover(
                app_dir=Path.cwd(), data_dir=Path(temporary) / "data"
            )
            paths.ensure_directories()
            window = MainWindow(paths, SettingsManager(paths))
            window.show()
            self.app.processEvents()

            sidebar = window.findChild(QWidget, "Sidebar")
            logo = window.findChild(QLabel, "BrandLogo")
            name = window.findChild(QLabel, "BrandName")

            self.assertIsNotNone(sidebar)
            self.assertIsNotNone(logo)
            self.assertIsNotNone(name)
            self.assertEqual(sidebar.width(), 264)  # type: ignore[union-attr]
            self.assertEqual(window.minimumWidth(), 1160)
            self.assertEqual(window.width(), 1360)
            self.assertEqual(logo.size().toTuple(), (72, 72))  # type: ignore[union-attr]
            self.assertIsNotNone(logo.pixmap())  # type: ignore[union-attr]
            self.assertFalse(logo.pixmap().isNull())  # type: ignore[union-attr]
            self.assertEqual(name.text(), "Apson\nYTDownloader")  # type: ignore[union-attr]
            self.assertGreaterEqual(name.width(), name.sizeHint().width())  # type: ignore[union-attr]
            window.close()

    def test_release_version_and_installer_fallback_are_consistent(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "packaging" / "windows" / "installer.iss").read_text(
            encoding="utf-8"
        )
        version_info = (
            project_root / "packaging" / "windows" / "version_info.txt"
        ).read_text(encoding="utf-8")

        self.assertEqual(__version__, "0.5.3")
        self.assertIn(f'#define AppVersion "{__version__}"', installer)
        self.assertIn(f"StringStruct('FileVersion', '{__version__}')", version_info)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", version_info)
        self.assertNotIn("ExpandConstant('{app}\\data')", installer)
        self.assertIn("AddBackslash(WizardDirValue) + 'data'", installer)

    def test_uninstaller_uses_guarded_opt_in_data_removal(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        installer = (project_root / "packaging" / "windows" / "installer.iss").read_text(
            encoding="utf-8"
        )

        self.assertIn("DataOwnerMarkerName = '.apson-ytdownloader-data'", installer)
        self.assertIn("SaveStringToFile(MarkerPath, DataOwnerMarkerContent", installer)
        self.assertIn("HasPurgeDataParameter", installer)
        self.assertIn("'/PURGEDATA=1'", installer)
        self.assertIn("MB_YESNO or MB_DEFBUTTON2", installer)
        self.assertIn("if (not DeleteData) and (not UninstallSilent)", installer)
        self.assertIn("IsSafeOwnedDataDirectory", installer)
        self.assertIn("PathIsRooted(DataDirectory)", installer)
        self.assertIn("LoadStringFromFile(MarkerPath, MarkerContent)", installer)
        for directory in (
            "settings",
            "cache",
            "history",
            "thumbnails",
            "temp",
            "logs",
            "downloads",
        ):
            self.assertIn(f"DeleteManagedDataDirectory('{directory}')", installer)
        self.assertNotIn("DelTree(UninstallDataDir", installer)
        self.assertIn("RemoveDir(UninstallDataDir)", installer)

    def test_distribution_includes_project_license_and_branding_policy(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        spec = (
            project_root / "packaging" / "windows" / "ApsonYTDownloader.spec"
        ).read_text(encoding="utf-8")

        self.assertTrue((project_root / "LICENSE").is_file())
        self.assertTrue((project_root / "BRANDING.md").is_file())
        self.assertIn('(str(PROJECT_ROOT / "LICENSE"), ".")', spec)
        self.assertIn('(str(PROJECT_ROOT / "BRANDING.md"), ".")', spec)


if __name__ == "__main__":
    unittest.main()
