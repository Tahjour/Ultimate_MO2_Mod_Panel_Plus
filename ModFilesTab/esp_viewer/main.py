import logging
import os
import sys
from typing import Optional

# Suppress Qt font warnings on Windows
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

if __name__ == "__main__" and __package__ is None:
    package_root = os.path.dirname(os.path.dirname(__file__))
    if package_root not in sys.path:
        sys.path.insert(0, package_root)

from PyQt6.QtWidgets import QApplication

from esp_viewer.ui.main_window import MainWindow


def _extract_language_and_path(argv: list[str]) -> tuple[Optional[str], Optional[str], list[str]]:
    language: Optional[str] = None
    filtered: list[str] = []
    expect_value = False
    for arg in argv:
        if expect_value:
            expect_value = False
            if arg:
                language = arg
            continue
        if arg in {"-l", "--language"}:
            expect_value = True
            continue
        if arg.startswith("-l:"):
            value = arg[3:]
            if value:
                language = value
            continue
        if arg.startswith("-l="):
            value = arg[3:]
            if value:
                language = value
            continue
        if arg.startswith("--language="):
            value = arg.split("=", 1)[1]
            if value:
                language = value
            continue
        filtered.append(arg)

    path: Optional[str] = None
    for arg in filtered:
        if os.path.isfile(arg):
            path = arg
            break

    return language, path, filtered


def launch_viewer(path: Optional[str] = None, language: Optional[str] = None, parent=None) -> MainWindow:
    if language:
        os.environ.setdefault("ESP_VIEWER_LANGUAGE", language)
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0]])
        app.setApplicationName("ESP/ESM/ESL Viewer")
    window = MainWindow(parent)
    window.show()
    if path:
        window.load_plugin(path)
    return window


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    language, path, app_args = _extract_language_and_path(sys.argv[1:])
    if language:
        os.environ.setdefault("ESP_VIEWER_LANGUAGE", language)
    app = QApplication([sys.argv[0], *app_args])
    app.setApplicationName("ESP/ESM/ESL Viewer")
    window = MainWindow()
    window.show()
    if path:
        window.load_plugin(path)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
