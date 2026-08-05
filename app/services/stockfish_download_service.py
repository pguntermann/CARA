"""Detect platform, resolve official Stockfish release assets, download and extract."""

from __future__ import annotations

import platform
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import requests


GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "CARA-Chess-GetStockfish",
}

DEFAULT_GITHUB_RELEASES_LATEST_URL = (
    "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
)
DEFAULT_OFFICIAL_DOWNLOAD_PAGE_URL = "https://stockfishchess.org/download/"


def classify_release_lookup_error(exc: BaseException) -> Tuple[str, str]:
    """Map a release-lookup exception to (kind, detail) for user-facing copy.

    Kinds: ``offline``, ``timeout``, ``http``, ``generic``.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover
        requests = None  # type: ignore

    if requests is not None:
        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout", ""
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "offline", ""
        if isinstance(exc, requests.exceptions.HTTPError):
            status = ""
            response = getattr(exc, "response", None)
            if response is not None and getattr(response, "status_code", None):
                status = str(response.status_code)
            return "http", status

    text = str(exc) or ""
    lower = text.lower()
    if any(
        token in lower
        for token in (
            "nameresolutionerror",
            "getaddrinfo failed",
            "failed to resolve",
            "nodename nor servname",
            "name or service not known",
            "network is unreachable",
            "temporary failure in name resolution",
        )
    ):
        return "offline", ""
    if "timed out" in lower or "timeout" in lower:
        return "timeout", ""
    if "max retries exceeded" in lower:
        return "offline", ""

    short = text.split("\n", 1)[0].strip()
    if len(short) > 160:
        short = short[:157] + "…"
    return "generic", short


@dataclass(frozen=True)
class PlatformInfo:
    """Detected host platform for binary selection."""

    os_family: str  # windows | macos | linux
    arch: str  # x86_64 | arm64
    display_name: str


@dataclass(frozen=True)
class StockfishBinaryOption:
    """One selectable Stockfish build variant for the current platform."""

    id: str
    label: str
    description: str
    # Substring matched against the GitHub asset filename (lowercased).
    asset_token: str
    recommended: bool = False


@dataclass(frozen=True)
class ResolvedStockfishAsset:
    """A concrete downloadable release asset."""

    option: StockfishBinaryOption
    download_url: str
    filename: str
    size_bytes: int
    release_tag: str
    release_name: str


def detect_platform() -> PlatformInfo:
    """Return OS/arch info used to recommend a Stockfish binary."""
    system = platform.system().lower()
    machine = (platform.machine() or "").lower()

    if machine in ("arm64", "aarch64"):
        arch = "arm64"
    elif machine in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif machine.startswith("arm"):
        arch = "arm64"
    else:
        arch = "x86_64"

    if system == "windows" or system.startswith("cygwin"):
        os_family = "windows"
        display = f"Windows ({arch})"
    elif system == "darwin":
        os_family = "macos"
        display = f"macOS ({'Apple Silicon' if arch == 'arm64' else 'Intel'})"
    else:
        os_family = "linux"
        display = f"Linux ({arch})"

    return PlatformInfo(os_family=os_family, arch=arch, display_name=display)


def binary_options_for_platform(info: PlatformInfo) -> List[StockfishBinaryOption]:
    """Catalog of known official builds for this platform (may be filtered by release)."""
    if info.os_family == "windows" and info.arch == "arm64":
        return [
            StockfishBinaryOption(
                id="windows-armv8",
                label="Windows ARM64",
                description="Recommended for Windows on ARM devices.",
                asset_token="windows-armv8.zip",
                recommended=True,
            ),
            StockfishBinaryOption(
                id="windows-armv8-dotprod",
                label="Windows ARM64 (dotprod)",
                description="Faster on ARM CPUs that support dot-product instructions.",
                asset_token="windows-armv8-dotprod.zip",
            ),
        ]

    if info.os_family == "windows":
        return [
            StockfishBinaryOption(
                id="windows-x86-64-avx2",
                label="Windows x86-64 AVX2",
                description="Recommended for most modern Intel/AMD PCs (2013+).",
                asset_token="windows-x86-64-avx2.zip",
                recommended=True,
            ),
            StockfishBinaryOption(
                id="windows-x86-64-bmi2",
                label="Windows x86-64 BMI2",
                description="Often slightly faster on recent Intel CPUs.",
                asset_token="windows-x86-64-bmi2.zip",
            ),
            StockfishBinaryOption(
                id="windows-x86-64-sse41-popcnt",
                label="Windows x86-64 SSE4.1",
                description="Safer choice for older 64-bit PCs without AVX2.",
                asset_token="windows-x86-64-sse41-popcnt.zip",
            ),
            StockfishBinaryOption(
                id="windows-x86-64",
                label="Windows x86-64 (baseline)",
                description="Widest compatibility; slowest of the 64-bit builds.",
                asset_token="windows-x86-64.zip",
            ),
        ]

    if info.os_family == "macos" and info.arch == "arm64":
        return [
            StockfishBinaryOption(
                id="macos-m1-apple-silicon",
                label="macOS Apple Silicon",
                description="Recommended for M1/M2/M3/M4 Macs.",
                asset_token="macos-m1-apple-silicon.tar",
                recommended=True,
            ),
        ]

    if info.os_family == "macos":
        return [
            StockfishBinaryOption(
                id="macos-x86-64-avx2",
                label="macOS Intel AVX2",
                description="Recommended for most Intel Macs.",
                asset_token="macos-x86-64-avx2.tar",
                recommended=True,
            ),
            StockfishBinaryOption(
                id="macos-x86-64-sse41-popcnt",
                label="macOS Intel SSE4.1",
                description="For older Intel Macs without AVX2.",
                asset_token="macos-x86-64-sse41-popcnt.tar",
            ),
            StockfishBinaryOption(
                id="macos-x86-64",
                label="macOS Intel (baseline)",
                description="Widest Intel Mac compatibility.",
                asset_token="macos-x86-64.tar",
            ),
        ]

    # Linux (ubuntu builds are the official Linux packages)
    if info.arch == "arm64":
        return [
            StockfishBinaryOption(
                id="android-armv8",
                label="Linux ARM64 (armv8 build)",
                description="Official ARM64 build (published as Android armv8; works on many aarch64 Linux systems).",
                asset_token="android-armv8.tar",
                recommended=True,
            ),
        ]

    return [
        StockfishBinaryOption(
            id="ubuntu-x86-64-avx2",
            label="Linux x86-64 AVX2",
            description="Recommended for most modern 64-bit Linux PCs.",
            asset_token="ubuntu-x86-64-avx2.tar",
            recommended=True,
        ),
        StockfishBinaryOption(
            id="ubuntu-x86-64-bmi2",
            label="Linux x86-64 BMI2",
            description="Often slightly faster on recent Intel CPUs.",
            asset_token="ubuntu-x86-64-bmi2.tar",
        ),
        StockfishBinaryOption(
            id="ubuntu-x86-64-sse41-popcnt",
            label="Linux x86-64 SSE4.1",
            description="Safer choice for older 64-bit CPUs without AVX2.",
            asset_token="ubuntu-x86-64-sse41-popcnt.tar",
        ),
        StockfishBinaryOption(
            id="ubuntu-x86-64",
            label="Linux x86-64 (baseline)",
            description="Widest compatibility; slowest of the 64-bit builds.",
            asset_token="ubuntu-x86-64.tar",
        ),
    ]


def default_install_directory() -> Path:
    """Suggested install folder under the CARA user-data / portable root."""
    from app.utils.path_resolver import resolve_data_file_path

    settings_path, _ = resolve_data_file_path("user_settings.json")
    return settings_path.parent / "engines" / "stockfish"


class StockfishDownloadService:
    """Resolve, download, and extract official Stockfish release binaries."""

    def __init__(
        self,
        timeout_seconds: float = 90.0,
        *,
        github_releases_latest_url: str = DEFAULT_GITHUB_RELEASES_LATEST_URL,
        official_download_page_url: str = DEFAULT_OFFICIAL_DOWNLOAD_PAGE_URL,
    ) -> None:
        self._timeout = timeout_seconds
        self.github_releases_latest_url = (
            github_releases_latest_url or DEFAULT_GITHUB_RELEASES_LATEST_URL
        )
        self.official_download_page_url = (
            official_download_page_url or DEFAULT_OFFICIAL_DOWNLOAD_PAGE_URL
        )

    def fetch_release_assets(self) -> Tuple[str, str, List[dict]]:
        """Return (tag, name, assets) for the latest GitHub release."""
        response = requests.get(
            self.github_releases_latest_url,
            headers=GITHUB_HEADERS,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        tag = str(payload.get("tag_name") or "")
        name = str(payload.get("name") or tag)
        assets = payload.get("assets") or []
        if not isinstance(assets, list) or not assets:
            raise RuntimeError("Latest Stockfish release has no downloadable assets.")
        return tag, name, assets

    def resolve_options(
        self,
        info: Optional[PlatformInfo] = None,
    ) -> Tuple[PlatformInfo, str, str, List[ResolvedStockfishAsset]]:
        """Detect platform, fetch release, and resolve available binary options."""
        platform_info = info or detect_platform()
        tag, release_name, assets = self.fetch_release_assets()
        catalog = binary_options_for_platform(platform_info)
        resolved: List[ResolvedStockfishAsset] = []

        for option in catalog:
            asset = self._find_asset(assets, option.asset_token)
            if asset is None:
                continue
            url = str(asset.get("browser_download_url") or "")
            filename = str(asset.get("name") or "")
            size = int(asset.get("size") or 0)
            if not url or not filename:
                continue
            resolved.append(
                ResolvedStockfishAsset(
                    option=option,
                    download_url=url,
                    filename=filename,
                    size_bytes=size,
                    release_tag=tag,
                    release_name=release_name,
                )
            )

        if not resolved:
            raise RuntimeError(
                f"No matching Stockfish binaries were found for {platform_info.display_name} "
                f"in release {tag or release_name}."
            )

        # Ensure exactly one recommended flag among available options.
        if not any(item.option.recommended for item in resolved):
            first = resolved[0]
            resolved[0] = ResolvedStockfishAsset(
                option=StockfishBinaryOption(
                    id=first.option.id,
                    label=first.option.label,
                    description=first.option.description,
                    asset_token=first.option.asset_token,
                    recommended=True,
                ),
                download_url=first.download_url,
                filename=first.filename,
                size_bytes=first.size_bytes,
                release_tag=first.release_tag,
                release_name=first.release_name,
            )

        return platform_info, tag, release_name, resolved

    @staticmethod
    def _find_asset(assets: Sequence[dict], token: str) -> Optional[dict]:
        token_l = token.lower()
        for asset in assets:
            name = str(asset.get("name") or "").lower()
            if token_l in name:
                return asset
        return None

    def download_and_extract(
        self,
        asset: ResolvedStockfishAsset,
        install_dir: Path,
        *,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Path:
        """Download ``asset`` into ``install_dir`` and return the engine executable path."""
        install_dir = Path(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        archive_path = install_dir / asset.filename
        self._download_file(
            asset.download_url,
            archive_path,
            expected_size=asset.size_bytes,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        extract_root = install_dir / _safe_stem(asset.filename)
        if extract_root.exists():
            shutil.rmtree(extract_root, ignore_errors=True)
        extract_root.mkdir(parents=True, exist_ok=True)

        self._extract_archive(archive_path, extract_root)
        try:
            archive_path.unlink(missing_ok=True)
        except OSError:
            pass

        executable = find_stockfish_executable(extract_root)
        if executable is None:
            raise RuntimeError(
                "Download succeeded, but no Stockfish executable was found in the archive."
            )

        _ensure_executable(executable)
        _clear_macos_quarantine(executable)
        return executable

    def _download_file(
        self,
        url: str,
        destination: Path,
        *,
        expected_size: int = 0,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass

        with requests.get(
            url,
            headers={"User-Agent": GITHUB_HEADERS["User-Agent"]},
            stream=True,
            timeout=self._timeout,
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or expected_size or 0)
            downloaded = 0
            with open(partial, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if cancel_check and cancel_check():
                        handle.close()
                        try:
                            partial.unlink()
                        except OSError:
                            pass
                        raise RuntimeError("Download cancelled.")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        partial.replace(destination)
        if progress_callback:
            final_size = destination.stat().st_size if destination.exists() else downloaded
            progress_callback(final_size, final_size if total <= 0 else total)

    @staticmethod
    def _extract_archive(archive_path: Path, destination: Path) -> None:
        name = archive_path.name.lower()
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(destination)
            return
        if name.endswith(".tar") or name.endswith(".tar.gz") or name.endswith(".tgz"):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(destination)
            return
        raise RuntimeError(f"Unsupported archive format: {archive_path.name}")


def find_stockfish_executable(root: Path) -> Optional[Path]:
    """Locate the Stockfish binary under an extracted release folder."""
    root = Path(root)
    if not root.exists():
        return None

    candidates: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.endswith(".nnue") or name.endswith(".txt") or name.endswith(".md"):
            continue
        if "stockfish" not in name:
            continue
        if platform.system().lower().startswith("win"):
            if name.endswith(".exe"):
                candidates.append(path)
        else:
            # Prefer extensionless binaries named stockfish*
            if "." not in path.suffix or path.suffix.lower() in ("", ".bin"):
                candidates.append(path)

    if not candidates:
        return None

    def _score(path: Path) -> Tuple[int, int, str]:
        name = path.name.lower()
        # Prefer exact-ish names over helper scripts
        exact = 0 if name.startswith("stockfish") else 1
        return (exact, len(str(path)), str(path).lower())

    candidates.sort(key=_score)
    return candidates[0]


def format_bytes(num_bytes: int) -> str:
    """Human-readable byte size for progress labels."""
    if num_bytes <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def _safe_stem(filename: str) -> str:
    stem = Path(filename).name
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip"):
        if stem.lower().endswith(suffix):
            return stem[: -len(suffix)]
    return Path(stem).stem


def _ensure_executable(path: Path) -> None:
    if platform.system().lower().startswith("win"):
        return
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    except OSError:
        pass


def _clear_macos_quarantine(path: Path) -> None:
    if platform.system().lower() != "darwin":
        return
    try:
        import subprocess

        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", str(path.parent)],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass
