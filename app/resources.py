"""Resolve source, external EXE and bundled image paths without using cwd."""

from dataclasses import dataclass
import logging
from pathlib import Path
import sys

from PySide6.QtGui import QImageReader, QPixmap

LOGGER = logging.getLogger(__name__)


def asset_candidates(source_root: Path | None = None,
                     executable: Path | None = None,
                     bundle_root: Path | None = None) -> list[Path]:
    if executable is None and getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        bundle_root = Path(sys._MEIPASS)
    if executable is not None:
        roots = [executable.parent]
        if bundle_root is not None:
            roots.append(bundle_root)
    else:
        roots = [source_root or Path(__file__).resolve().parent.parent]
    return list(dict.fromkeys(root / "assets" / "overlay.jpg" for root in roots))


@dataclass
class OverlayAsset:
    pixmap: QPixmap
    message: str


def load_overlay(candidates: list[Path] | None = None) -> OverlayAsset:
    for path in candidates if candidates is not None else asset_candidates():
        if not path.is_file():
            continue
        reader = QImageReader(str(path))
        reader.setAutoTransform(False)
        image = reader.read()
        if not image.isNull():
            return OverlayAsset(QPixmap.fromImage(image), "已加载本地图片（仅在此设备使用）")
        LOGGER.warning("Local overlay could not be decoded; using text fallback")
        return OverlayAsset(QPixmap(), "本地图片无法读取，将使用白底休息提示。可替换 assets/overlay.jpg。")
    LOGGER.info("No local overlay provided; using text fallback")
    return OverlayAsset(QPixmap(), "未提供本地图片，将使用白底休息提示。可自行放入 assets/overlay.jpg。")


def resource_path(name: str) -> Path:
    """Fixed V1.1 assets: source root or internal frozen resource root only."""
    if Path(name).name != name:
        raise ValueError("Resource must be a filename")
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "assets" / name


def fallback_asset() -> OverlayAsset:
    return load_overlay([resource_path("fallback_overlay.jpg")])
