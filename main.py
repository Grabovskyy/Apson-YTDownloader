from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from app import __version__
from app.core.external_activation import ExternalActivation, ExternalActivationError
from app.core.settings_manager import SettingsManager
from app.core.single_instance import SingleInstanceCoordinator
from app.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET
from app.utils.logging_config import configure_logging
from app.utils.paths import AppPaths
from app.utils.runtime_environment import configure_runtime_environment


def create_qt_application(argv: list[str] | None = None) -> QApplication:
    """Create the lightweight Qt shell used by both primary and secondary launches."""
    QCoreApplication.setOrganizationName("Apson")
    QCoreApplication.setApplicationName("Apson YTDownloader")
    QCoreApplication.setApplicationVersion(__version__)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    app = QApplication(argv if argv is not None else sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    return app


def create_main_window() -> MainWindow:
    """Create writable paths and the main dependency graph for the primary instance."""
    paths = AppPaths.discover()
    paths.ensure_directories()
    configure_runtime_environment(paths)
    configure_logging(paths)
    settings = SettingsManager(paths)
    return MainWindow(paths=paths, settings=settings)


def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    """Compatibility helper used by smoke tests and interactive development."""
    app = create_qt_application(argv)
    return app, create_main_window()


def main() -> int:
    if "--analysis-helper" in sys.argv:
        from app.workers.analysis_helper import main as helper_main

        return helper_main()
    if "--self-test" in sys.argv:
        from app.core.self_test import run_self_test

        index = sys.argv.index("--self-test")
        report = (
            Path(sys.argv[index + 1]).expanduser().resolve()
            if index + 1 < len(sys.argv) and not sys.argv[index + 1].startswith("--")
            else None
        )
        return run_self_test(report)
    try:
        activation = ExternalActivation.from_argv(sys.argv)
    except ExternalActivationError:
        return 2

    app = create_qt_application([sys.argv[0]])
    coordinator = SingleInstanceCoordinator(parent=app)
    if coordinator.forward_to_running(activation):
        return 0
    if not coordinator.listen():
        return 3
    window = create_main_window()
    coordinator.activation_received.connect(window.handle_external_activation)
    window.show()
    if activation is not None:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: window.handle_external_activation(activation))
    result = app.exec()
    coordinator.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
