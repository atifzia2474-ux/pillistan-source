from pathlib import Path
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPixmap


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_LOGO = APP_ROOT / "assets" / "Full logo.jpg"


def get_logo_path():
    settings = QSettings("ZAO Enterprises", "Pillistan")
    configured = str(settings.value("business/logo_path", "") or "").strip()

    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return candidate

    if DEFAULT_LOGO.is_file():
        return DEFAULT_LOGO

    return None


def get_logo_pixmap(width=None, height=None):
    path = get_logo_path()
    if path is None:
        return QPixmap()

    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return QPixmap()

    if width and height:
        pixmap = pixmap.scaled(
            width, height,
            aspectMode=Qt.KeepAspectRatio,
            mode=Qt.SmoothTransformation
        )
    return pixmap
