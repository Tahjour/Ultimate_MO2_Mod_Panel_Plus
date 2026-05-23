"""ESP/ESM/ESL viewer package based on SSEEdit concepts."""

from typing import List


try:
    import mobase  # type: ignore[assignment]
except Exception:
    mobase = None  # type: ignore[assignment]
else:
    import os
    import subprocess

    class EspViewerPreview(mobase.IPluginPreview):  # type: ignore[misc]
        _organizer: mobase.IOrganizer

        def __init__(self) -> None:
            super().__init__()

        def init(self, organizer: "mobase.IOrganizer"):
            self._organizer = organizer
            return True

        def name(self) -> str:
            return "ESPViewerPreview"

        def localizedName(self) -> str:
            return self._tr("ESP/ESM/ESL Viewer")

        def author(self) -> str:
            return "esp_viewer"

        def description(self) -> str:
            return self._tr("Preview ESP/ESM/ESL plugins")

        def version(self) -> "mobase.VersionInfo":
            return mobase.VersionInfo(0, 1, 0, mobase.ReleaseType.BETA)

        def isActive(self) -> bool:
            return self._organizer.pluginSetting(self.name(), "enabled")

        def settings(self) -> List["mobase.PluginSetting"]:
            return [
                mobase.PluginSetting("enabled", "Enable esp_viewer preview plugin", True),
                mobase.PluginSetting(
                    "pythonPath",
                    "Python executable with PySide6 (for external viewer)",
                    "python",
                ),
            ]

        def displayName(self) -> str:
            return self.localizedName()

        def tooltip(self) -> str:
            return self.description()

        def icon(self):
            return self._organizer.gameIcon()

        def priority(self) -> int:
            return 0

        def supportedExtensions(self) -> List[str]:
            return ["esp", "esm", "esl"]

        def preview(self, fileName: str, parent=None):
            root = os.path.dirname(__file__)
            script = os.path.join(root, "main.py")
            python = self._organizer.pluginSetting(self.name(), "pythonPath") or "python"
            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(
                    [python, script, fileName], creationflags=creationflags
                )
            except Exception:
                # Ошибки запуска внешнего процесса оставляем в логах MO2
                pass
            return None

        def _tr(self, text: str) -> str:
            return text


    def createPlugin() -> "mobase.IPlugin":  # type: ignore[misc]
        return EspViewerPreview()
