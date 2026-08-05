"""Controller for the Get Stockfish wizard."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from app.controllers.engine_controller import EngineController
from app.services.engine_validation_service import EngineValidationService
from app.services.stockfish_download_service import (
    PlatformInfo,
    ResolvedStockfishAsset,
    StockfishDownloadService,
    classify_release_lookup_error,
    default_install_directory,
    detect_platform,
    format_bytes,
)


class _StockfishFetchWorker(QObject):
    finished = pyqtSignal(object, str, str, object)  # info, tag, name, options
    failed = pyqtSignal(str, str)  # kind, detail

    def __init__(self, service: StockfishDownloadService) -> None:
        super().__init__()
        self._service = service

    @pyqtSlot()
    def run(self) -> None:
        try:
            info, tag, name, options = self._service.resolve_options()
            self.finished.emit(info, str(tag or ""), str(name or ""), list(options))
        except Exception as exc:
            kind, detail = classify_release_lookup_error(exc)
            self.failed.emit(kind, detail)


class _StockfishInstallWorker(QObject):
    progress = pyqtSignal(int, int)  # downloaded, total
    finished = pyqtSignal(object)  # Path
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: StockfishDownloadService,
        asset: ResolvedStockfishAsset,
        install_dir: Path,
    ) -> None:
        super().__init__()
        self._service = service
        self._asset = asset
        self._install_dir = install_dir
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @pyqtSlot()
    def run(self) -> None:
        try:
            path = self._service.download_and_extract(
                self._asset,
                self._install_dir,
                progress_callback=lambda d, t: self.progress.emit(int(d), int(t)),
                cancel_check=lambda: self._cancel,
            )
            self.finished.emit(path)
        except Exception as exc:
            self.failed.emit(str(exc) or "Download failed.")


class _StockfishValidateWorker(QObject):
    finished = pyqtSignal(object)  # EngineValidationResult
    failed = pyqtSignal(str)

    def __init__(self, executable: Path) -> None:
        super().__init__()
        self._executable = Path(executable)

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = EngineValidationService.validate_engine(
                self._executable, save_to_file=True
            )
            if not result.is_valid:
                self.failed.emit(
                    result.error_message or "Engine validation failed."
                )
                return
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc) or "Engine validation failed.")


class GetStockfishController(QObject):
    """Orchestrates platform detection, download, and engine registration."""

    options_ready = pyqtSignal(object, str, str, object)  # PlatformInfo, tag, name, list
    options_failed = pyqtSignal(str, str)  # kind, detail
    download_progress = pyqtSignal(int, int)
    download_finished = pyqtSignal(object)  # Path
    download_failed = pyqtSignal(str)
    validation_finished = pyqtSignal(str)  # success message
    validation_failed = pyqtSignal(str)

    def __init__(self, engine_controller: EngineController, config=None, parent=None) -> None:
        super().__init__(parent)
        self._engine_controller = engine_controller
        gs_cfg = {}
        if isinstance(config, dict):
            gs_cfg = (
                (config.get("ui") or {})
                .get("dialogs", {})
                .get("get_stockfish", {})
            )
        self._service = StockfishDownloadService(
            github_releases_latest_url=str(
                gs_cfg.get("github_releases_latest_url") or ""
            ),
            official_download_page_url=str(
                gs_cfg.get("official_download_page_url") or ""
            ),
        )
        self.official_download_page_url = self._service.official_download_page_url
        self._platform = detect_platform()
        self._options: List[ResolvedStockfishAsset] = []
        self._selected: Optional[ResolvedStockfishAsset] = None
        self._install_dir = default_install_directory()
        self._release_tag = ""
        self._release_name = ""
        self._fetch_thread: Optional[QThread] = None
        self._fetch_worker: Optional[_StockfishFetchWorker] = None
        self._install_thread: Optional[QThread] = None
        self._install_worker: Optional[_StockfishInstallWorker] = None
        self._validate_thread: Optional[QThread] = None
        self._validate_worker: Optional[_StockfishValidateWorker] = None
        self._downloaded_executable: Optional[Path] = None

    @property
    def platform_info(self) -> PlatformInfo:
        return self._platform

    @property
    def install_directory(self) -> Path:
        return self._install_dir

    @property
    def release_label(self) -> str:
        if self._release_name:
            return self._release_name
        return self._release_tag or "latest"

    @property
    def options(self) -> List[ResolvedStockfishAsset]:
        return list(self._options)

    @property
    def selected_asset(self) -> Optional[ResolvedStockfishAsset]:
        return self._selected

    @property
    def downloaded_executable(self) -> Optional[Path]:
        return self._downloaded_executable

    def set_install_directory(self, path: Path) -> None:
        self._install_dir = Path(path)

    def set_selected_option_id(self, option_id: str) -> None:
        for asset in self._options:
            if asset.option.id == option_id:
                self._selected = asset
                return

    def recommended_option_id(self) -> Optional[str]:
        for asset in self._options:
            if asset.option.recommended:
                return asset.option.id
        return self._options[0].option.id if self._options else None

    def format_asset_size(self, asset: ResolvedStockfishAsset) -> str:
        return format_bytes(asset.size_bytes)

    def start_fetch_options(self) -> None:
        self._cleanup_fetch_thread()

        thread = QThread(self)
        worker = _StockfishFetchWorker(self._service)
        worker.moveToThread(thread)

        # Keep strong refs — local-only workers get GC'd before run() fires.
        self._fetch_thread = thread
        self._fetch_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_fetch_finished)
        worker.failed.connect(self._on_fetch_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_fetch_thread_finished)

        thread.start()

    @pyqtSlot(object, str, str, object)
    def _on_fetch_finished(self, info, tag: str, name: str, options) -> None:
        self._platform = info
        self._release_tag = tag or ""
        self._release_name = name or ""
        self._options = list(options or [])
        rec = self.recommended_option_id()
        if rec:
            self.set_selected_option_id(rec)
        self.options_ready.emit(
            info, self._release_tag, self._release_name, self._options
        )

    @pyqtSlot(str, str)
    def _on_fetch_failed(self, kind: str, detail: str) -> None:
        self.options_failed.emit(kind, detail)

    @pyqtSlot()
    def _on_fetch_thread_finished(self) -> None:
        worker = self._fetch_worker
        thread = self._fetch_thread
        self._fetch_worker = None
        self._fetch_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    def start_download(self) -> None:
        if self._selected is None:
            self.download_failed.emit("No Stockfish build is selected.")
            return
        self._cleanup_install_thread()

        thread = QThread(self)
        worker = _StockfishInstallWorker(
            self._service, self._selected, self._install_dir
        )
        worker.moveToThread(thread)

        self._install_thread = thread
        self._install_worker = worker

        thread.started.connect(worker.run)
        worker.progress.connect(self.download_progress.emit)
        worker.finished.connect(self._on_install_finished)
        worker.failed.connect(self._on_install_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_install_thread_finished)

        thread.start()

    @pyqtSlot(object)
    def _on_install_finished(self, path) -> None:
        self._downloaded_executable = Path(str(path))
        self.download_finished.emit(self._downloaded_executable)

    @pyqtSlot(str)
    def _on_install_failed(self, message: str) -> None:
        self.download_failed.emit(message)

    @pyqtSlot()
    def _on_install_thread_finished(self) -> None:
        worker = self._install_worker
        thread = self._install_thread
        self._install_worker = None
        self._install_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    def cancel_download(self) -> None:
        if self._install_worker is not None:
            self._install_worker.cancel()

    def start_validation(self, executable: Optional[Path] = None) -> None:
        """Validate the downloaded binary on a worker thread, then register it."""
        path = Path(executable) if executable is not None else self._downloaded_executable
        if path is None:
            self.validation_failed.emit("No downloaded Stockfish executable to validate.")
            return
        self._downloaded_executable = path
        self._cleanup_validate_thread()

        thread = QThread(self)
        worker = _StockfishValidateWorker(path)
        worker.moveToThread(thread)

        self._validate_thread = thread
        self._validate_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_validate_finished)
        worker.failed.connect(self._on_validate_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_validate_thread_finished)

        thread.start()

    @pyqtSlot(object)
    def _on_validate_finished(self, result) -> None:
        path = self._downloaded_executable
        if path is None:
            self.validation_failed.emit(
                "No downloaded Stockfish executable to register."
            )
            return
        name = getattr(result, "name", None) or "Stockfish"
        author = getattr(result, "author", None) or "the Stockfish developers"
        version = (
            getattr(result, "version", None)
            or self._release_tag.replace("sf_", "")
            or ""
        )
        # Register on the GUI thread — engine model emits Qt signals.
        success, message, _engine = self._engine_controller.add_engine(
            path, name, author, version
        )
        if success:
            self.validation_finished.emit(message)
        else:
            self.validation_failed.emit(message or "Could not add engine.")

    @pyqtSlot(str)
    def _on_validate_failed(self, message: str) -> None:
        self.validation_failed.emit(message)

    @pyqtSlot()
    def _on_validate_thread_finished(self) -> None:
        worker = self._validate_worker
        thread = self._validate_thread
        self._validate_worker = None
        self._validate_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    def cleanup(self) -> None:
        self.cancel_download()
        self._cleanup_fetch_thread()
        self._cleanup_install_thread()
        self._cleanup_validate_thread()

    def _cleanup_fetch_thread(self) -> None:
        thread = self._fetch_thread
        if thread is None:
            return
        if thread.isRunning():
            thread.quit()
            thread.wait(2000)
        self._fetch_worker = None
        self._fetch_thread = None

    def _cleanup_install_thread(self) -> None:
        thread = self._install_thread
        if thread is None:
            return
        if thread.isRunning():
            if self._install_worker is not None:
                self._install_worker.cancel()
            thread.quit()
            thread.wait(2000)
        self._install_worker = None
        self._install_thread = None

    def _cleanup_validate_thread(self) -> None:
        thread = self._validate_thread
        if thread is None:
            return
        if thread.isRunning():
            thread.quit()
            thread.wait(6000)
        self._validate_worker = None
        self._validate_thread = None
