import os
import logging
from pathlib import Path
from typing import Set, Dict, List, Optional
from esp_viewer.core.bsa_index import parse_bsa_index, ArchiveIndex
from esp_viewer.core.plugin_file import parse_plugin
from esp_viewer.core.data_types import PluginFile, Record, Group
from esp_viewer.core.localization import decode_text

logger = logging.getLogger(__name__)

class AssetManager:
    """Менеджер для индексации и поиска ассетов в Skyrim."""
    
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.loose_files: Set[str] = set()
        self.archives: Dict[str, ArchiveIndex] = {}
        self.all_files_normalized: Set[str] = set()
        
    def index_all(self, load_order: List[str]):
        """Индексирует все файлы: сначала Loose, потом BSA в порядке load order."""
        self._index_loose()
        self._index_archives(load_order)
        self._build_flat_index()

    def find_unused_assets(self, used_assets: Set[str]) -> Set[str]:
        """Находит ассеты, которые есть в файлах, но не используются в плагинах."""
        used_normalized = {p.lower().replace('/', '\\') for p in used_assets}
        unused = set()
        for asset_path in self.all_files_normalized:
            # Игнорируем системные файлы и сами плагины
            if asset_path.endswith(('.esp', '.esm', '.esl', '.txt', '.ini')):
                continue
            if asset_path not in used_normalized:
                unused.add(asset_path)
        return unused

    def _index_loose(self):
        """Сканирует папку Data на наличие Loose файлов."""
        logger.info(f"Indexing loose files in {self.data_path}")
        for root, _, files in os.walk(self.data_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.data_path)
                self.loose_files.add(rel_path.lower())

    def _index_archives(self, load_order: List[str]):
        """Индексирует BSA/BA2 архивы в соответствии с порядком загрузки."""
        # В Скайриме архивы грузятся вместе с плагинами.
        # Для каждого плагина <name>.esp могут быть <name> - Assets.bsa, <name> - Textures.bsa и т.д.
        for plugin_name in load_order:
            base_name = os.path.splitext(plugin_name)[0]
            # Поиск связанных архивов
            for ext in ['.bsa', '.ba2']:
                # Обычный архив
                self._try_load_archive(base_name + ext)
                # Архивы с суффиксами (Skyrim SE/AE)
                self._try_load_archive(base_name + " - Textures" + ext)
                self._try_load_archive(base_name + " - Meshes" + ext)
                self._try_load_archive(base_name + " - Assets" + ext)
                self._try_load_archive(base_name + " - Sounds" + ext)
                self._try_load_archive(base_name + " - Voices" + ext)

    def _try_load_archive(self, archive_name: str):
        archive_path = self.data_path / archive_name
        if archive_path.exists():
            logger.info(f"Indexing archive: {archive_name}")
            idx = parse_bsa_index(archive_path)
            if idx:
                self.archives[archive_name.lower()] = idx

    def _build_flat_index(self):
        """Создает общий список всех доступных путей (в нижнем регистре)."""
        self.all_files_normalized.update(self.loose_files)
        for archive in self.archives.values():
            for entry in archive.files:
                self.all_files_normalized.add(entry.path.lower().replace('/', '\\'))

    def file_exists(self, path: str) -> bool:
        """Проверяет существование файла в индексе."""
        return path.lower().replace('/', '\\') in self.all_files_normalized

class AssetScanner:
    """Сканер плагинов на наличие ссылок на ассеты."""
    
    ASSET_SIGNATURES = {
        'MODL', # Model
        'MOD2', 'MOD3', 'MOD4', # Alternate models
        'ICON', # Icon / Large texture
        'MICO', # Menu icon
        'TX00', 'TX01', 'TX02', 'TX03', 'TX04', 'TX05', 'TX06', 'TX07', # Texture Set
        'MNAM', # Иногда содержит пути
    }
    
    ASSET_EXTENSIONS = {'.nif', '.dds', '.tga', '.wav', '.mp3', '.fuz', '.hkx'}

    def __init__(self, asset_manager: AssetManager):
        self.manager = asset_manager
        self.missing_assets: Dict[str, List[Dict]] = {} # path -> list of (plugin, formid, record_type)
        self.used_assets: Set[str] = set()

    def scan_plugin(self, plugin_path: str):
        plugin_name = os.path.basename(plugin_path)
        logger.info(f"Scanning plugin: {plugin_name}")
        
        try:
            plugin = parse_plugin(plugin_path)
        except Exception as e:
            logger.error(f"Failed to parse plugin {plugin_name}: {e}")
            return

        def walk(node):
            if isinstance(node, Record):
                self._scan_record(node, plugin_name)
            elif isinstance(node, Group):
                for child in node.children:
                    walk(child)

        for child in plugin.children:
            walk(child)

    def _scan_record(self, record: Record, plugin_name: str):
        for field in record.fields:
            if field.signature in self.ASSET_SIGNATURES:
                path = decode_text(field.raw)
                if path:
                    self._check_asset(path, record, plugin_name, field.signature)
            else:
                # На всякий случай проверяем все строки на расширения, 
                # так как ассеты могут быть в неожиданных полях
                try:
                    # Пробуем декодировать как строку, если размер позволяет
                    if 4 < field.size < 512:
                        text = decode_text(field.raw)
                        if text and any(text.lower().endswith(ext) for ext in self.ASSET_EXTENSIONS):
                            self._check_asset(text, record, plugin_name, field.signature)
                except:
                    pass

    def _check_asset(self, path: str, record: Record, plugin_name: str, field_sig: str):
        # Очистка пути (иногда бывают лишние пробелы или нули)
        path = path.strip('\x00').strip()
        if not path:
            return
            
        self.used_assets.add(path)
            
        if not self.manager.file_exists(path):
            if path not in self.missing_assets:
                self.missing_assets[path] = []
            
            self.missing_assets[path].append({
                'plugin': plugin_name,
                'form_id': hex(record.form_id),
                'signature': record.signature,
                'field': field_sig,
                'editor_id': record.editor_id
            })

    def report(self):
        """Выводит отчет о потерянных ассетах."""
        if self.missing_assets:
            print(f"\nОбнаружено {len(self.missing_assets)} отсутствующих ассетов:")
            for path, occurrences in self.missing_assets.items():
                print(f"\n[MISSING] {path}")
                for occ in occurrences:
                    print(f"  - В плагине: {occ['plugin']}")
                    print(f"    Запись: {occ['signature']} ({occ['form_id']}) - {occ['editor_id']}")
                    print(f"    Поле: {occ['field']}")
        else:
            print("\nОтсутствующих ассетов не обнаружено.")

        unused = self.manager.find_unused_assets(self.used_assets)
        if unused:
            print(f"\nОбнаружено {len(unused)} неиспользуемых ассетов (орфанов):")
            # Выводим первые 20 для примера
            for path in sorted(list(unused))[:20]:
                print(f"  - [UNUSED] {path}")
            if len(unused) > 20:
                print(f"  ... и еще {len(unused) - 20} файлов.")
        else:
            print("\nНеиспользуемых ассетов не обнаружено.")

if __name__ == "__main__":
    # Пример использования (нужно указать реальный путь к Data)
    DATA_PATH = r"C:\Games\Skyrim Special Edition\Data"
    if os.path.exists(DATA_PATH):
        manager = AssetManager(DATA_PATH)
        # В реальности список плагинов нужно брать из loadorder.txt
        plugins = [f for f in os.listdir(DATA_PATH) if f.lower().endswith(('.esp', '.esm', '.esl'))]
        
        manager.index_all(plugins)
        
        scanner = AssetScanner(manager)
        for p in plugins:
            scanner.scan_plugin(os.path.join(DATA_PATH, p))
            
        scanner.report()
    else:
        print(f"Путь {DATA_PATH} не найден. Укажите корректный путь к папке Data Skyrim.")
