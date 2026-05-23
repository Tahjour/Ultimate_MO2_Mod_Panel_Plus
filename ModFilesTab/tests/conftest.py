import sys
from unittest.mock import MagicMock

# Mock mobase module before any imports
sys.modules["mobase"] = MagicMock()

# Mock PyQt6 modules to avoid DLL load errors in headless environment
sys.modules["PyQt6"] = MagicMock()
sys.modules["PyQt6.QtCore"] = MagicMock()
sys.modules["PyQt6.QtWidgets"] = MagicMock()
sys.modules["PyQt6.QtGui"] = MagicMock()
