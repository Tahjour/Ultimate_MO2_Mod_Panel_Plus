import logging
import os
from typing import Dict, List, Tuple, Any, Set
from PyQt6.QtCore import QThread, pyqtSignal as Signal

from esp_viewer.core.plugin_file import create_lazy_index, parse_record_at_offset
from esp_viewer.core.data_types import LazyPluginIndex

logger = logging.getLogger(__name__)

class EspStructureLoader(QThread):
    """
    Загрузчик структуры ESP, использующий ленивую индексацию (как в основном вьювере).
    Это обеспечивает мгновенное открытие даже огромных плагинов (Skyrim.esm).
    """
    # Сигнал отправляется для каждого плагина отдельно: (esp_path, data)
    pluginDataReady = Signal(str, object)
    # Сигнал об окончании всей работы
    allFinished = Signal()

    # Целевые поля для поиска путей (согласно требованиям)
    TARGET_FIELDS: Set[str] = {
        # Модели
        "MODL", "MOD2", "MOD3", "MOD4", "MOD5", "DMDL",
        "NAM0", "NAM1", "NAM2", "NAM3",
        # Текстуры
        "TX00", "TX01", "TX02", "TX03", "TX04", "TX05", "TX06", "TX07",
        # Звуки
        "FNAM", "ANAM", "SNAM",
    }

    # Расширения для валидации путей в сомнительных полях (ANAM, SNAM)
    ASSET_EXTENSIONS = (
        ".nif", ".dds", ".tga", ".wav", ".xwm", ".fuz", ".mp3", ".ogg",
        ".tri", ".kf", ".hkx", ".psc", ".pex", ".swf", ".gfx"
    )

    def __init__(self, esp_paths: List[str], cache: Dict[str, Any] = None, parent=None) -> None:
        super().__init__(parent)
        self.esp_paths = esp_paths
        self.cache = cache if cache is not None else {}
        self._is_canceled = False

    def stop(self):
        self._is_canceled = True

    def run(self) -> None:
        logger.info(f"Loader thread started execution for {len(self.esp_paths)} paths")
        
        # Даем UI-потоку время гарантированно обработать соединения (на всякий случай)
        self.msleep(10)
        
        for path in self.esp_paths:
            if self._is_canceled:
                logger.info("Loader CANCELED before/during plugin processing")
                break

            try:
                if not os.path.exists(path):
                    self.pluginDataReady.emit(path, "File not found")
                    continue
                
                # Используем кэш, если он есть
                if path in self.cache:
                    logger.info(f"Using cached data for {path}")
                    self.pluginDataReady.emit(path, self.cache[path])
                    continue

                logger.info(f"Starting lazy indexing for {path}")
                # Используем МГНОВЕННЫЙ ленивый индекс (создается за миллисекунды)
                lazy_index = create_lazy_index(path)
                
                # Анализируем записи по смещениям из индекса
                logger.info(f"Analyzing {len(lazy_index.record_offsets)} records in {path}")
                esp_data = self._analyze_via_index(lazy_index)
                
                # Сохраняем в кэш
                self.cache[path] = esp_data
                
                # Отправляем данные одного плагина в UI
                logger.info(f"Emitting data for {path}")
                self.pluginDataReady.emit(path, esp_data)
                
            except Exception as e:
                logger.error(f"Error indexing plugin {path}: {e}", exc_info=True)
                self.pluginDataReady.emit(path, f"Error: {str(e)}")

        if not self._is_canceled:
            logger.info("All plugins analyzed, emitting allFinished signal.")
            self.allFinished.emit()

    def _analyze_via_index(self, index: LazyPluginIndex) -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
        """Анализирует плагин, читая только заголовки записей и целевые поля."""
        esp_data = {}
        
        # Перебираем все найденные записи в индексе
        total_records = len(index.record_offsets)
        processed = 0
        
        for (sig, form_id), offset in index.record_offsets.items():
            processed += 1
            if self._is_canceled:
                break
                
            # Даем GUI потоку передышку каждые 100 записей
            if processed % 100 == 0:
                self.msleep(1)
                
            # Парсим конкретную запись по её смещению
            try:
                record = parse_record_at_offset(index.path, offset, index.header_size)
                
                record_assets = []
                for field in record.fields:
                    if field.signature in self.TARGET_FIELDS:
                        try:
                            # Извлекаем путь (аналогично тому, как это делает xEdit)
                            val_bytes = field.raw.split(b"\x00")[0]
                            if len(val_bytes) < 4:
                                continue
                                
                            val = val_bytes.decode("ascii", errors="ignore").strip()
                            
                            # Валидация для звуков
                            if field.signature in ("ANAM", "SNAM"):
                                if not val.lower().endswith(self.ASSET_EXTENSIONS):
                                    continue
                                    
                            record_assets.append((field.signature, val))
                        except:
                            continue
                
                if record_assets:
                    if sig not in esp_data:
                        esp_data[sig] = {}
                    
                    # Используем EditorID или FormID
                    rec_id = record.editor_id or f"0x{form_id:08X}"
                    esp_data[sig][rec_id] = record_assets
                    
            except Exception as e:
                # Если одна запись битая, просто идем дальше
                continue
                
        return esp_data
