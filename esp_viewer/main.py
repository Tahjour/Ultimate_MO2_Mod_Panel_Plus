import logging
import os
import sys
import argparse
from typing import Optional, List, Tuple

# Suppress Qt font warnings on Windows
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"

if __name__ == "__main__" and __package__ is None:
    package_root = os.path.dirname(os.path.dirname(__file__))
    if package_root not in sys.path:
        sys.path.insert(0, package_root)

from PyQt6.QtWidgets import QApplication, QWidget

from esp_viewer.ui.main_window import MainWindow


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESP/ESM/ESL Viewer for Bethesda Games")
    parser.add_argument("path", nargs="?", help="Path to the plugin file to load")
    parser.add_argument("-l", "--language", help="Set the interface language (e.g., 'en', 'ru')")
    return parser.parse_args(argv)


def launch_viewer(path: Optional[str] = None, language: Optional[str] = None, parent: Optional[QWidget] = None) -> MainWindow:
    """
    Launches the ESP Viewer window.
    
    Args:
        path: Optional path to a plugin file to load.
        language: Optional language code for the UI.
        parent: Optional parent QWidget.
        
    Returns:
        The created MainWindow instance.
    """
    if language:
        os.environ["ESP_VIEWER_LANGUAGE"] = language
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
        app.setApplicationName("ESP/ESM/ESL Viewer")
    
    window = MainWindow(parent)
    window.show()
    if path and os.path.isfile(path):
        window.load_plugin(path)
    return window


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    args = _parse_args(sys.argv[1:])
    
    if args.language:
        os.environ["ESP_VIEWER_LANGUAGE"] = args.language
        
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ESP/ESM/ESL Viewer")
    
    window = MainWindow()
    window.show()
    
    if args.path and os.path.isfile(args.path):
        window.load_plugin(args.path)
        
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
