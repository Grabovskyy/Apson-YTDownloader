from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QThreadPool, QTimer, QUrl, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.external_activation import ExternalActivation, ExternalActivationError
from app.core.history_store import HistoryEntry, HistoryStatus, HistoryStore
from app.core.models import MediaItem, MediaStatus
from app.core.queue_manager import QueueManager
from app.core.settings_manager import SettingsManager, VideoPlaylistBehavior
from app.core.toolchain_manager import ToolchainError, ToolchainManager, load_tools_manifest
from app.services.downloader import (
    DownloadProgress,
    DownloadResult,
    DownloadStage,
    Downloader,
)
from app.services.media_analyzer import AnalysisOptions, AnalysisResult, MediaAnalyzer
from app.ui.widgets.download_queue_table import DownloadQueueTable
from app.ui.widgets.history_table import HistoryTable
from app.ui.widgets.queue_table import QueueTable
from app.utils.paths import AppPaths
from app.workers.analysis_process import AnalysisProcessController
from app.workers.analysis_worker import AnalysisWorker
from app.workers.download_queue_worker import DownloadQueueWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        paths: AppPaths,
        settings: SettingsManager,
        *,
        analyzer: MediaAnalyzer | None = None,
        downloader: Downloader | None = None,
        toolchain_manager: ToolchainManager | None = None,
        thread_pool: QThreadPool | None = None,
        history_store: HistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.queue = QueueManager()
        self.history = history_store or HistoryStore(paths)
        self.toolchain_manager = toolchain_manager or ToolchainManager(paths)
        self.analyzer = analyzer
        try:
            self.analysis_toolchain = self.toolchain_manager.resolve(validate=False)
        except ToolchainError:
            self.analysis_toolchain = None
        self.downloader = downloader
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self._analysis_worker: AnalysisWorker | AnalysisProcessController | None = None
        self._analysis_errors: list[tuple[str, str]] = []
        self._analysis_added = 0
        self._analysis_truncated: list[int] = []
        self._active_analysis_urls: set[str] = set()
        self._pending_external_urls: list[str] = []
        self._pending_external_set: set[str] = set()
        self._download_worker: DownloadQueueWorker | None = None
        self._download_items: tuple[MediaItem, ...] = ()
        self._download_errors: list[tuple[str, str]] = []
        self._download_quality_by_id: dict[str, str] = {}
        self._history_recorded_ids: set[str] = set()
        self._closing = False

        self.setWindowTitle("Apson YTDownloader")
        icon_path = self.paths.assets_dir / "icons" / "apson-ytdownloader.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(1160, 720)
        self.resize(1360, 820)
        self._build_ui()
        self._load_settings_into_ui()
        self._refresh_queue()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_downloader_page())
        self.pages.addWidget(self._build_download_queue_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_settings_page())
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self._build_status_bar()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(264)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 26, 20, 22)
        layout.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        brand_logo = QLabel()
        brand_logo.setObjectName("BrandLogo")
        brand_logo.setFixedSize(72, 72)
        logo_path = self.paths.assets_dir / "branding" / "piratecat.png"
        if logo_path.is_file():
            pixmap = QPixmap(str(logo_path))
            brand_logo.setPixmap(
                pixmap.scaled(
                    brand_logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_logo.setToolTip("Apson YTDownloader")
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel("Apson\nYTDownloader")
        name.setObjectName("BrandName")
        caption = QLabel("AUDIO TOOLKIT")
        caption.setObjectName("BrandCaption")
        brand_text.addWidget(name)
        brand_text.addWidget(caption)
        brand_row.addWidget(brand_logo)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(30)

        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        entries = (
            ("  ↓   Downloader", 0),
            ("  ≡   Kolejka", 1),
            ("  ◷   Historia", 2),
            ("  ⚙   Ustawienia", 3),
        )
        for label, index in entries:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page=index: self.pages.setCurrentIndex(page))
            self.navigation.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        layout.addStretch(1)
        version = QLabel(f"Wersja {__version__}  •  MP3")
        version.setObjectName("MutedLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        return sidebar

    def _build_downloader_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(38, 28, 38, 24)
        outer.setSpacing(18)

        title = QLabel("Pobierz audio")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Wklej jeden lub kilka adresów. Playlisty zostaną rozpoznane automatycznie.")
        subtitle.setObjectName("PageSubtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addWidget(self._build_url_card())
        outer.addWidget(self._build_results_card(), 1)
        outer.addWidget(self._build_options_card())
        return page

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        return frame, layout

    def _build_url_card(self) -> QFrame:
        card, layout = self._card()
        title_row = QHBoxLayout()
        section_title = QLabel("Adresy materiałów")
        section_title.setObjectName("SectionTitle")
        hint = QLabel("Każdy adres umieść w osobnym wierszu")
        hint.setObjectName("MutedLabel")
        title_row.addWidget(section_title)
        title_row.addStretch(1)
        title_row.addWidget(hint)
        layout.addLayout(title_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=…\nhttps://www.youtube.com/playlist?list=…")
        self.url_input.setFixedHeight(76)
        self.url_input.setAcceptRichText(False)
        self.analyze_button = QPushButton("Analizuj")
        self.analyze_button.setObjectName("PrimaryButton")
        self.analyze_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.analyze_button.setFixedSize(126, 76)
        self.analyze_button.clicked.connect(self._analyze_urls)
        input_row.addWidget(self.url_input, 1)
        input_row.addWidget(self.analyze_button)
        layout.addLayout(input_row)
        return card

    def _build_results_card(self) -> QFrame:
        card, layout = self._card()
        controls = QHBoxLayout()
        section_title = QLabel("Wyniki analizy")
        section_title.setObjectName("SectionTitle")
        controls.addWidget(section_title)
        controls.addSpacing(10)

        select_all = QPushButton("Zaznacz wszystko")
        select_all.clicked.connect(self._select_all)
        clear_selection = QPushButton("Odznacz wszystko")
        clear_selection.clicked.connect(self._clear_selection)
        remove_selected = QPushButton("Usuń zaznaczone")
        remove_selected.setObjectName("DangerGhost")
        remove_selected.clicked.connect(self._remove_selected)
        controls.addWidget(select_all)
        controls.addWidget(clear_selection)
        controls.addWidget(remove_selected)
        controls.addStretch(1)
        self.counter_label = QLabel("0 elementów")
        self.counter_label.setObjectName("CounterLabel")
        controls.addWidget(self.counter_label)
        layout.addLayout(controls)

        self.queue_table = QueueTable(self._set_item_selection)
        layout.addWidget(self.queue_table, 1)
        return card

    def _build_options_card(self) -> QFrame:
        card, layout = self._card()
        row = QHBoxLayout()
        row.setSpacing(12)

        format_column = QVBoxLayout()
        format_label = QLabel("FORMAT")
        format_label.setObjectName("MutedLabel")
        self.format_combo = QComboBox()
        self.format_combo.addItem("MP3")
        self.format_combo.setFixedWidth(104)
        format_column.addWidget(format_label)
        format_column.addWidget(self.format_combo)

        quality_column = QVBoxLayout()
        quality_label = QLabel("JAKOŚĆ")
        quality_label.setObjectName("MutedLabel")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["128 kbps", "192 kbps", "256 kbps", "320 kbps"])
        self.quality_combo.setFixedWidth(128)
        quality_column.addWidget(quality_label)
        quality_column.addWidget(self.quality_combo)

        folder_column = QVBoxLayout()
        folder_label = QLabel("FOLDER DOCELOWY")
        folder_label.setObjectName("MutedLabel")
        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit()
        self.folder_input.setMinimumWidth(260)
        browse_button = QPushButton("Wybierz…")
        browse_button.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder_input, 1)
        folder_row.addWidget(browse_button)
        folder_column.addWidget(folder_label)
        folder_column.addLayout(folder_row)

        self.download_button = QPushButton("↓  Pobierz zaznaczone")
        self.download_button.setObjectName("DownloadButton")
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setMinimumWidth(226)
        self.download_button.clicked.connect(self._prepare_downloads)

        row.addLayout(format_column)
        row.addLayout(quality_column)
        row.addLayout(folder_column, 1)
        row.addWidget(self.download_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(row)
        return card

    def _build_download_queue_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(38, 28, 38, 28)
        outer.setSpacing(18)

        title = QLabel("Kolejka pobierania")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Materiały są pobierane kolejno, jeden po drugim.")
        subtitle.setObjectName("PageSubtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        card, layout = self._card()
        controls = QHBoxLayout()
        self.download_queue_summary = QLabel("Kolejka jest pusta")
        self.download_queue_summary.setObjectName("SectionTitle")
        self.cancel_current_button = QPushButton("Anuluj bieżący")
        self.cancel_current_button.clicked.connect(self._cancel_current_download)
        self.cancel_all_button = QPushButton("Anuluj wszystko")
        self.cancel_all_button.setObjectName("DangerGhost")
        self.cancel_all_button.clicked.connect(self._cancel_all_downloads)
        self.clear_finished_button = QPushButton("Wyczyść zakończone")
        self.clear_finished_button.clicked.connect(self._clear_finished_downloads)
        controls.addWidget(self.download_queue_summary)
        controls.addStretch(1)
        controls.addWidget(self.cancel_current_button)
        controls.addWidget(self.cancel_all_button)
        controls.addWidget(self.clear_finished_button)
        layout.addLayout(controls)

        self.download_queue_table = DownloadQueueTable()
        layout.addWidget(self.download_queue_table, 1)
        outer.addWidget(card, 1)
        self._set_download_controls_active(False)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 28, 38, 28)
        layout.setSpacing(18)
        title = QLabel("Historia")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Wyniki zakończonych pobrań, błędów i anulowanych zadań.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card, card_layout = self._card()
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Pokaż:"))
        self.history_filter = QComboBox()
        self.history_filter.addItem("Wszystkie", "all")
        for status in HistoryStatus:
            self.history_filter.addItem(status.value, status.value)
        self.history_filter.currentIndexChanged.connect(self._refresh_history)
        controls.addWidget(self.history_filter)
        controls.addStretch(1)
        open_file = QPushButton("Otwórz plik")
        open_file.clicked.connect(self._open_history_file)
        open_folder = QPushButton("Otwórz folder")
        open_folder.clicked.connect(self._open_history_folder)
        remove = QPushButton("Usuń zaznaczone")
        remove.clicked.connect(self._remove_history_entries)
        clear = QPushButton("Wyczyść historię")
        clear.setObjectName("DangerGhost")
        clear.clicked.connect(self._clear_history)
        controls.addWidget(open_file)
        controls.addWidget(open_folder)
        controls.addWidget(remove)
        controls.addWidget(clear)
        card_layout.addLayout(controls)
        self.history_table = HistoryTable()
        self.history_table.cellDoubleClicked.connect(
            lambda _row, _column: self._open_history_file()
        )
        card_layout.addWidget(self.history_table, 1)
        layout.addWidget(card, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(38, 28, 38, 28)
        layout.setSpacing(18)
        title = QLabel("Ustawienia")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Zachowanie analizy, pobierania oraz używane lokalizacje danych.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        analysis_card, analysis_layout = self._card()
        analysis_layout.addWidget(self._section_title("Analiza"))
        analysis_row = QHBoxLayout()
        behavior_column = QVBoxLayout()
        behavior_column.addWidget(QLabel("FILM Z KONTEKSTEM PLAYLISTY"))
        self.settings_playlist_behavior = QComboBox()
        self.settings_playlist_behavior.addItem(
            "Analizuj tylko wskazany film", VideoPlaylistBehavior.SINGLE_VIDEO.value
        )
        self.settings_playlist_behavior.addItem(
            "Analizuj całą playlistę", VideoPlaylistBehavior.FULL_PLAYLIST.value
        )
        behavior_column.addWidget(self.settings_playlist_behavior)
        limit_column = QVBoxLayout()
        limit_column.addWidget(QLabel("LIMIT POZYCJI PLAYLISTY"))
        self.settings_playlist_limit = QSpinBox()
        self.settings_playlist_limit.setRange(1, 10_000)
        self.settings_playlist_limit.setSuffix(" pozycji")
        limit_column.addWidget(self.settings_playlist_limit)
        timeout_column = QVBoxLayout()
        timeout_column.addWidget(QLabel("LIMIT CZASU JEDNEGO URL"))
        self.settings_analysis_timeout = QSpinBox()
        self.settings_analysis_timeout.setRange(15, 600)
        self.settings_analysis_timeout.setSuffix(" s")
        timeout_column.addWidget(self.settings_analysis_timeout)
        analysis_row.addLayout(behavior_column, 2)
        analysis_row.addLayout(limit_column, 1)
        analysis_row.addLayout(timeout_column, 1)
        analysis_layout.addLayout(analysis_row)
        layout.addWidget(analysis_card)

        download_card, download_layout = self._card()
        download_layout.addWidget(self._section_title("Pobieranie"))
        download_row = QHBoxLayout()
        folder_column = QVBoxLayout()
        folder_column.addWidget(QLabel("DOMYŚLNY FOLDER POBIERANIA"))
        folder_row = QHBoxLayout()
        self.settings_download_folder = QLineEdit()
        settings_browse = QPushButton("Wybierz…")
        settings_browse.clicked.connect(self._choose_settings_folder)
        folder_row.addWidget(self.settings_download_folder, 1)
        folder_row.addWidget(settings_browse)
        folder_column.addLayout(folder_row)
        quality_column = QVBoxLayout()
        quality_column.addWidget(QLabel("DOMYŚLNA JAKOŚĆ MP3"))
        self.settings_audio_quality = QComboBox()
        self.settings_audio_quality.addItems(
            ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
        )
        quality_column.addWidget(self.settings_audio_quality)
        download_row.addLayout(folder_column, 3)
        download_row.addLayout(quality_column, 1)
        download_layout.addLayout(download_row)
        layout.addWidget(download_card)

        data_card, data_layout = self._card()
        data_layout.addWidget(self._section_title("Dane i narzędzia"))
        for label, path in (
            ("Dane", self.paths.data_dir),
            ("Cache", self.paths.cache_dir),
            ("Historia", self.paths.history_dir),
            ("Pliki tymczasowe", self.paths.temp_dir),
            ("Logi", self.paths.logs_dir),
            ("Pobrania", self.paths.downloads_dir),
        ):
            row = QHBoxLayout()
            name = QLabel(f"{label}:")
            name.setFixedWidth(135)
            value = QLabel(str(path))
            value.setObjectName("MutedLabel")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(name)
            row.addWidget(value, 1)
            data_layout.addLayout(row)
        toolchain_label = QLabel(self._toolchain_summary())
        toolchain_label.setObjectName("MutedLabel")
        toolchain_label.setWordWrap(True)
        data_layout.addWidget(toolchain_label)
        layout.addWidget(data_card, 1)

        browser_card, browser_layout = self._card()
        browser_layout.addWidget(self._section_title("Integracja z przeglądarką"))
        browser_description = QLabel(
            "Zainstalowana wersja może odbierać bieżący adres strony przez "
            "jednoklikową zakładkę. Przy pierwszym użyciu przeglądarka może "
            "poprosić o zgodę na otwarcie aplikacji."
        )
        browser_description.setObjectName("MutedLabel")
        browser_description.setWordWrap(True)
        browser_layout.addWidget(browser_description)
        browser_buttons = QHBoxLayout()
        open_instructions = QPushButton("Otwórz instrukcję przycisku")
        open_instructions.clicked.connect(self._open_browser_instructions)
        copy_bookmarklet = QPushButton("Skopiuj kod zakładki")
        copy_bookmarklet.clicked.connect(self._copy_browser_bookmarklet)
        browser_buttons.addWidget(open_instructions)
        browser_buttons.addWidget(copy_bookmarklet)
        browser_buttons.addStretch(1)
        browser_layout.addLayout(browser_buttons)
        layout.addWidget(browser_card)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_button = QPushButton("Zapisz ustawienia")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self._save_settings_from_ui)
        save_row.addWidget(save_button)
        layout.addLayout(save_row)
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def _toolchain_summary(self) -> str:
        try:
            manifest = load_tools_manifest(self.paths.app_dir / "tools-manifest.json")
            versions = ", ".join(
                f"{tool['name']} {tool['version']}"
                for tool in manifest["tools"]
                if isinstance(tool, dict)
            )
        except (OSError, ValueError, KeyError):
            versions = "nie udało się odczytać manifestu"
        state = "binaria obecne" if self.analysis_toolchain is not None else "brak binariów"
        return f"Toolchain: {versions} • {state} • {self.paths.bin_dir}"

    @staticmethod
    def _browser_bookmarklet() -> str:
        return (
            "javascript:(()=>{location.href='apson-ytdownloader://add?url='+"
            "encodeURIComponent(location.href)})()"
        )

    def _open_browser_instructions(self) -> None:
        instructions = self.paths.assets_dir / "browser" / "install-button.html"
        if not instructions.is_file():
            QMessageBox.warning(
                self, "Brak instrukcji", f"Nie znaleziono pliku:\n{instructions}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(instructions)))

    def _copy_browser_bookmarklet(self) -> None:
        QApplication.clipboard().setText(self._browser_bookmarklet())
        self.status_label.setText("●  Kod zakładki skopiowany do schowka")

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        status.setContentsMargins(14, 2, 18, 2)
        self.status_label = QLabel("●  Gotowy")
        self.status_label.setObjectName("MutedLabel")
        self.global_progress = QProgressBar()
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(0)
        self.global_progress.setFixedWidth(220)
        self.global_progress.setTextVisible(False)
        status.addWidget(self.status_label)
        status.addPermanentWidget(self.global_progress)
        self.setStatusBar(status)

    def _load_settings_into_ui(self) -> None:
        values = self.settings.values
        self.folder_input.setText(values.download_folder)
        self.format_combo.setCurrentText(values.audio_format)
        self.quality_combo.setCurrentText(values.audio_quality)
        self.settings_download_folder.setText(values.download_folder)
        self.settings_audio_quality.setCurrentText(values.audio_quality)
        behavior_index = self.settings_playlist_behavior.findData(
            values.video_playlist_behavior
        )
        self.settings_playlist_behavior.setCurrentIndex(max(0, behavior_index))
        self.settings_playlist_limit.setValue(values.playlist_item_limit)
        self.settings_analysis_timeout.setValue(values.analysis_timeout_seconds)
        self._refresh_history()

    def _choose_settings_folder(self) -> None:
        current = Path(self.settings_download_folder.text()).expanduser()
        initial = str(current if current.is_dir() else self.paths.downloads_dir)
        chosen = QFileDialog.getExistingDirectory(
            self, "Wybierz domyślny folder pobierania", initial
        )
        if chosen:
            self.settings_download_folder.setText(chosen)

    def _save_settings_from_ui(self) -> None:
        folder_text = self.settings_download_folder.text().strip()
        if not folder_text:
            QMessageBox.warning(
                self, "Niepoprawne ustawienia", "Folder pobierania nie może być pusty."
            )
            return
        try:
            self.settings.update(
                download_folder=folder_text,
                audio_quality=self.settings_audio_quality.currentText(),
                audio_format="MP3",
                video_playlist_behavior=str(
                    self.settings_playlist_behavior.currentData()
                ),
                playlist_item_limit=self.settings_playlist_limit.value(),
                analysis_timeout_seconds=self.settings_analysis_timeout.value(),
            )
        except (OSError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "Nie można zapisać ustawień", str(error))
            return
        self.folder_input.setText(folder_text)
        self.quality_combo.setCurrentText(self.settings_audio_quality.currentText())
        self.status_label.setText("●  Ustawienia zapisane")

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_table"):
            return
        selected_filter = self.history_filter.currentData()
        entries = self.history.entries
        if selected_filter != "all":
            entries = tuple(
                entry for entry in entries if entry.status.value == selected_filter
            )
        self.history_table.set_entries(entries)

    def _open_history_file(self) -> None:
        entry = self.history_table.current_entry()
        if entry is None or not entry.output_path:
            self.status_label.setText("●  Ten wpis nie ma pliku wynikowego")
            return
        path = Path(entry.output_path)
        if not path.is_file():
            QMessageBox.warning(self, "Brak pliku", f"Plik już nie istnieje:\n{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_history_folder(self) -> None:
        entry = self.history_table.current_entry()
        if entry is None or not entry.output_path:
            self.status_label.setText("●  Ten wpis nie ma folderu wynikowego")
            return
        folder = Path(entry.output_path).parent
        if not folder.is_dir():
            QMessageBox.warning(self, "Brak folderu", f"Folder już nie istnieje:\n{folder}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _remove_history_entries(self) -> None:
        entry_ids = self.history_table.selected_entry_ids()
        if not entry_ids:
            self.status_label.setText("●  Zaznacz wpisy historii do usunięcia")
            return
        removed = self.history.remove(entry_ids)
        self._refresh_history()
        self.status_label.setText(f"●  Usunięto {removed} wpisów historii")

    def _clear_history(self) -> None:
        if not self.history.entries:
            return
        answer = QMessageBox.question(
            self,
            "Wyczyść historię",
            "Usunąć wszystkie wpisy historii? Pobrane pliki MP3 pozostaną na dysku.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.history.clear()
        self._refresh_history()
        self.status_label.setText("●  Historia została wyczyszczona")

    def _analyze_urls(self) -> None:
        if self._analysis_worker is not None:
            self._cancel_analysis()
            return

        urls, invalid_urls = self._validated_urls(self.url_input.toPlainText().splitlines())
        if not urls and not invalid_urls:
            self.status_label.setText("●  Wklej co najmniej jeden adres")
            self.url_input.setFocus()
            return
        if not urls:
            self.status_label.setText("●  Nie znaleziono poprawnych adresów HTTP/HTTPS")
            QMessageBox.warning(
                self,
                "Niepoprawne adresy",
                "Każdy adres musi być pełnym adresem HTTP lub HTTPS.",
            )
            return

        self._start_analysis_batch(urls, invalid_urls)

    def _start_analysis_batch(
        self, urls: list[str], invalid_urls: list[str] | None = None
    ) -> None:
        if self._analysis_worker is not None or not urls:
            return

        self._analysis_errors = [
            (url, "Niepoprawny adres HTTP/HTTPS.")
            for url in (invalid_urls or [])
        ]
        self._analysis_added = 0
        self._analysis_truncated = []
        self._active_analysis_urls = set(urls)
        values = self.settings.values
        options = AnalysisOptions(
            video_playlist_behavior=values.video_playlist_behavior,
            playlist_item_limit=values.playlist_item_limit,
        )
        if self.analyzer is not None:
            worker: AnalysisWorker | AnalysisProcessController = AnalysisWorker(
                urls, self.analyzer, options
            )
            signals = worker.signals
        else:
            worker = AnalysisProcessController(
                urls,
                self.paths,
                options,
                values.analysis_timeout_seconds,
                self.analysis_toolchain,
                self,
            )
            signals = worker
        signals.started.connect(self._on_analysis_started)
        signals.items_found.connect(self._on_analysis_items)
        signals.url_failed.connect(self._on_analysis_error)
        signals.status_changed.connect(self._on_analysis_status)
        signals.finished.connect(self._on_analysis_finished)
        self._analysis_worker = worker
        self._set_analysis_active(True)
        if isinstance(worker, AnalysisProcessController):
            QTimer.singleShot(0, worker.start)
        else:
            self.thread_pool.start(worker)

    def handle_external_activation(self, activation: ExternalActivation) -> None:
        if self._closing:
            return
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if not activation.url:
            return
        try:
            url = ExternalActivation.validate_web_url(activation.url)
        except ExternalActivationError as error:
            self.status_label.setText(f"●  Odrzucono link zewnętrzny: {error}")
            return
        self._append_url_to_input(url)
        if not activation.auto_analyze:
            self.status_label.setText("●  Dodano link z przeglądarki")
            return
        if self._analysis_worker is not None:
            if url not in self._active_analysis_urls and url not in self._pending_external_set:
                self._pending_external_urls.append(url)
                self._pending_external_set.add(url)
            self.status_label.setText(
                f"●  Link z przeglądarki oczekuje • {len(self._pending_external_urls)} w kolejce"
            )
            return
        self._start_analysis_batch([url])

    def _append_url_to_input(self, url: str) -> None:
        existing = [line.strip() for line in self.url_input.toPlainText().splitlines()]
        if url in existing:
            return
        text = self.url_input.toPlainText().rstrip()
        self.url_input.setPlainText(f"{text}\n{url}".lstrip())

    @staticmethod
    def _validated_urls(lines: list[str]) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()
        for line in lines:
            url = line.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            parsed = urlparse(url)
            if parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc):
                valid.append(url)
            else:
                invalid.append(url)
        return valid, invalid

    def _set_analysis_active(self, active: bool) -> None:
        self.url_input.setEnabled(not active)
        self.analyze_button.setText("Anuluj" if active else "Analizuj")
        self.analyze_button.setEnabled(True)
        if active:
            self.global_progress.setRange(0, 0)
        else:
            self.global_progress.setRange(0, 100)
            if self._download_worker is not None:
                self._update_global_download_progress()
            else:
                self.global_progress.setValue(0)

    def _cancel_analysis(self) -> None:
        if self._analysis_worker is None:
            return
        self._analysis_worker.cancel()
        self.analyze_button.setEnabled(False)
        self.status_label.setText("●  Anulowanie analizy…")

    def _on_analysis_started(self) -> None:
        if not self._closing:
            self.status_label.setText("●  Rozpoczynanie analizy…")

    def _on_analysis_status(self, message: str) -> None:
        if not self._closing:
            self.status_label.setText(f"●  {message}")

    def _on_analysis_items(self, source_url: str, result: object) -> None:
        del source_url
        if self._closing or not isinstance(result, AnalysisResult):
            return
        self._analysis_added += self.queue.add_many_unique(list(result.items))
        if result.truncated:
            self._analysis_truncated.append(len(result.items))
        self._refresh_queue()

    def _on_analysis_error(self, url: str, message: str) -> None:
        if not self._closing:
            self._analysis_errors.append((url, message))

    def _on_analysis_finished(
        self, cancelled: bool, successful_urls: int, failed_urls: int
    ) -> None:
        del failed_urls
        completed_worker = self._analysis_worker
        self._analysis_worker = None
        if isinstance(completed_worker, AnalysisProcessController):
            completed_worker.deleteLater()
        if self._closing:
            return

        self._set_analysis_active(False)
        if cancelled:
            self.status_label.setText(
                f"●  Analiza anulowana • zachowano {self._analysis_added} elementów"
            )
        elif successful_urls:
            if self._analysis_truncated:
                limit = self.settings.values.playlist_item_limit
                self.status_label.setText(
                    f"●  Dodano pierwsze {limit} pozycji • limit zmienisz w Ustawieniach"
                )
            else:
                self.status_label.setText(
                    f"●  Analiza zakończona • dodano {self._analysis_added} elementów"
                )
        else:
            self.status_label.setText("●  Analiza nie zwróciła żadnych elementów")

        if self._analysis_errors and not cancelled:
            shown = self._analysis_errors[:5]
            details = "\n\n".join(f"{url}\n{message}" for url, message in shown)
            remaining = len(self._analysis_errors) - len(shown)
            if remaining:
                details += f"\n\n…oraz {remaining} kolejnych błędów."
            QMessageBox.warning(
                self,
                "Nie wszystkie adresy przeanalizowano",
                details,
            )
        self._active_analysis_urls.clear()
        if self._pending_external_urls:
            pending = list(self._pending_external_urls)
            self._pending_external_urls.clear()
            self._pending_external_set.clear()
            self.status_label.setText(
                f"●  Uruchamianie {len(pending)} linków z przeglądarki…"
            )
            QTimer.singleShot(0, lambda urls=pending: self._start_analysis_batch(urls))

    def _refresh_queue(self) -> None:
        items = self.queue.items
        self.queue_table.set_items(items)
        count = len(items)
        selected = len(self.queue.selected_items)
        noun = "element" if count == 1 else "elementy" if 2 <= count <= 4 else "elementów"
        self.counter_label.setText(f"{count} {noun}  •  zaznaczono {selected}")
        self.download_button.setEnabled(selected > 0 and self._download_worker is None)

    def _set_item_selection(self, item_id: str, selected: bool) -> None:
        self.queue.set_selected(item_id, selected)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        count = len(self.queue.items)
        selected = len(self.queue.selected_items)
        noun = "element" if count == 1 else "elementy" if 2 <= count <= 4 else "elementów"
        self.counter_label.setText(f"{count} {noun}  •  zaznaczono {selected}")
        self.download_button.setEnabled(selected > 0 and self._download_worker is None)

    def _select_all(self) -> None:
        self.queue.select_all()
        self._refresh_queue()

    def _clear_selection(self) -> None:
        self.queue.clear_selection()
        self._refresh_queue()

    def _remove_selected(self) -> None:
        if self._download_worker is not None:
            self.status_label.setText("●  Nie można usuwać elementów podczas pobierania")
            return
        removed = self.queue.remove_selected()
        self._refresh_queue()
        self.status_label.setText(f"●  Usunięto {removed} elementów" if removed else "●  Brak zaznaczonych elementów")

    def _choose_folder(self) -> None:
        current = Path(self.folder_input.text()).expanduser()
        initial = str(current if current.is_dir() else self.paths.downloads_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Wybierz folder docelowy", initial)
        if chosen:
            self.folder_input.setText(chosen)
            self.settings.update(download_folder=chosen)
            self.settings_download_folder.setText(chosen)

    def _prepare_downloads(self) -> None:
        if self._download_worker is not None:
            return
        selected = self.queue.selected_items
        if not selected:
            return
        output = Path(self.folder_input.text().strip()).expanduser()
        if not self.folder_input.text().strip():
            output = self.paths.downloads_dir
            self.folder_input.setText(str(output))

        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Nie można użyć folderu",
                f"Nie udało się utworzyć folderu docelowego:\n{output}\n\n{error}",
            )
            return

        self.settings.update(
            download_folder=str(output),
            audio_format=self.format_combo.currentText(),
            audio_quality=self.quality_combo.currentText(),
        )
        self.settings_download_folder.setText(str(output))
        self.settings_audio_quality.setCurrentText(self.quality_combo.currentText())
        if self.downloader is None:
            try:
                toolchain = self.toolchain_manager.resolve(validate=True)
            except ToolchainError as error:
                QMessageBox.warning(self, "Brak toolchainu", error.user_message)
                self.status_label.setText("●  Brakuje FFmpeg, ffprobe lub Deno")
                return
            self.downloader = Downloader(self.paths, toolchain)

        try:
            requests = self.downloader.create_requests(
                selected,
                output,
                self.format_combo.currentText(),
                self.quality_combo.currentText(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Niepoprawne ustawienia", str(error))
            return

        for item in selected:
            item.status = MediaStatus.QUEUED
            item.progress = 0
        self._download_items = selected
        self._download_errors = []
        self._download_quality_by_id = {
            request.item_id: request.quality for request in requests
        }
        self._history_recorded_ids = set()
        self.download_queue_table.set_items(self._download_items)
        self._refresh_queue()

        worker = DownloadQueueWorker(requests, self.downloader)
        worker.signals.queue_started.connect(self._on_download_queue_started)
        worker.signals.item_started.connect(self._on_download_item_started)
        worker.signals.item_progress.connect(self._on_download_progress)
        worker.signals.item_completed.connect(self._on_download_item_completed)
        worker.signals.item_failed.connect(self._on_download_item_failed)
        worker.signals.item_cancelled.connect(self._on_download_item_cancelled)
        worker.signals.queue_finished.connect(self._on_download_queue_finished)
        self._download_worker = worker
        self._set_download_controls_active(True)
        self.cancel_current_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.pages.setCurrentIndex(1)
        queue_button = self.navigation.button(1)
        if queue_button is not None:
            queue_button.setChecked(True)
        self.thread_pool.start(worker)

    def _set_download_controls_active(self, active: bool) -> None:
        self.cancel_current_button.setEnabled(active)
        self.cancel_all_button.setEnabled(active)
        self.clear_finished_button.setEnabled(not active and bool(self._download_items))

    def _on_download_queue_started(self, total: int) -> None:
        if self._closing:
            return
        self.download_queue_summary.setText(f"0 z {total} ukończonych")
        self.status_label.setText(f"●  Uruchomiono kolejkę: {total} zadań")

    def _on_download_item_started(self, item_id: str) -> None:
        if self._closing:
            return
        item = self.queue.get(item_id)
        if item is None:
            return
        item.status = MediaStatus.DOWNLOADING
        self.queue_table.update_item(item)
        self.download_queue_table.update_item(item)
        self.cancel_current_button.setEnabled(True)
        if self._analysis_worker is None:
            self.status_label.setText(f"●  Pobieranie: {item.title}")

    def _on_download_progress(self, value: object) -> None:
        if self._closing or not isinstance(value, DownloadProgress):
            return
        item = self.queue.get(value.item_id)
        if item is None:
            return
        item.progress = min(100, max(0, round(value.percent)))
        if value.stage == DownloadStage.CONVERTING:
            item.status = MediaStatus.CONVERTING
        elif value.stage == DownloadStage.COMPLETED:
            item.status = MediaStatus.COMPLETED
        else:
            item.status = MediaStatus.DOWNLOADING
        self.queue_table.update_item(item)
        self.download_queue_table.update_item(item, value)
        if self._analysis_worker is None:
            self._update_global_download_progress()

    def _on_download_item_completed(self, item_id: str, result: object) -> None:
        item = self.queue.get(item_id)
        if item is None or self._closing:
            return
        item.status = MediaStatus.COMPLETED
        item.progress = 100
        self.queue_table.update_item(item)
        self.download_queue_table.update_item(item)
        self.cancel_current_button.setEnabled(False)
        if isinstance(result, DownloadResult):
            self._record_history(
                item,
                HistoryStatus.SKIPPED_EXISTING
                if result.skipped_existing
                else HistoryStatus.DOWNLOADED,
                output_path=result.output_path,
            )
        self._update_download_summary()

    def _on_download_item_failed(self, item_id: str, message: str) -> None:
        item = self.queue.get(item_id)
        if item is None or self._closing:
            return
        item.status = MediaStatus.ERROR
        self._download_errors.append((item.title, message))
        self.queue_table.update_item(item)
        self.download_queue_table.update_item(item)
        self.cancel_current_button.setEnabled(False)
        self._record_history(item, HistoryStatus.ERROR, error_message=message)
        self._update_download_summary()

    def _on_download_item_cancelled(self, item_id: str) -> None:
        item = self.queue.get(item_id)
        if item is None or self._closing:
            return
        item.status = MediaStatus.CANCELLED
        self.queue_table.update_item(item)
        self.download_queue_table.update_item(item)
        self.cancel_current_button.setEnabled(False)
        self._record_history(item, HistoryStatus.CANCELLED)
        self._update_download_summary()

    def _record_history(
        self,
        item: MediaItem,
        status: HistoryStatus,
        *,
        output_path: Path | None = None,
        error_message: str | None = None,
    ) -> None:
        if item.id in self._history_recorded_ids:
            return
        entry = HistoryEntry.create(
            title=item.title,
            author=item.author,
            source_url=item.url,
            source_id=item.source_id,
            quality=self._download_quality_by_id.get(
                item.id, self.settings.values.audio_quality
            ),
            status=status,
            output_path=output_path,
            error_message=error_message,
        )
        try:
            self.history.add(entry)
        except OSError as error:
            self.status_label.setText(f"●  Nie udało się zapisać historii: {error}")
            return
        self._history_recorded_ids.add(item.id)
        self._refresh_history()

    def _on_download_queue_finished(
        self, stopped: bool, completed: int, failed: int, cancelled: int
    ) -> None:
        self._download_worker = None
        if self._closing:
            return
        self._set_download_controls_active(False)
        self.clear_finished_button.setEnabled(bool(self._download_items))
        self._update_selection_summary()
        self._update_global_download_progress()
        if stopped:
            state = "Kolejka anulowana"
        else:
            state = "Kolejka zakończona"
        self.status_label.setText(
            f"●  {state} • ukończono {completed}, błędy {failed}, anulowano {cancelled}"
        )
        self.download_queue_summary.setText(
            f"Ukończono {completed} • błędy {failed} • anulowano {cancelled}"
        )
        if self._download_errors:
            details = "\n\n".join(
                f"{title}\n{message}" for title, message in self._download_errors[:5]
            )
            QMessageBox.warning(self, "Błędy pobierania", details)

    def _cancel_current_download(self) -> None:
        if self._download_worker is not None:
            self._download_worker.cancel_current()
            self.cancel_current_button.setEnabled(False)
            self.status_label.setText("●  Anulowanie bieżącego zadania…")

    def _cancel_all_downloads(self) -> None:
        if self._download_worker is not None:
            self._download_worker.cancel_all()
            self.cancel_current_button.setEnabled(False)
            self.cancel_all_button.setEnabled(False)
            self.status_label.setText("●  Anulowanie całej kolejki…")

    def _clear_finished_downloads(self) -> None:
        terminal = {MediaStatus.COMPLETED, MediaStatus.ERROR, MediaStatus.CANCELLED}
        self._download_items = tuple(
            item for item in self._download_items if item.status not in terminal
        )
        self.download_queue_table.set_items(self._download_items)
        self.clear_finished_button.setEnabled(bool(self._download_items))
        self._update_download_summary()

    def _update_download_summary(self) -> None:
        total = len(self._download_items)
        finished = sum(
            item.status in {MediaStatus.COMPLETED, MediaStatus.ERROR, MediaStatus.CANCELLED}
            for item in self._download_items
        )
        self.download_queue_summary.setText(
            f"{finished} z {total} zakończonych" if total else "Kolejka jest pusta"
        )

    def _update_global_download_progress(self) -> None:
        if not self._download_items:
            self.global_progress.setValue(0)
            return
        average = round(sum(item.progress for item in self._download_items) / len(self._download_items))
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(average)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        if self._analysis_worker is not None:
            if isinstance(self._analysis_worker, AnalysisProcessController):
                self._analysis_worker.shutdown()
            else:
                self._analysis_worker.cancel()
        if self._download_worker is not None:
            self._download_worker.cancel_all()
        event.accept()
