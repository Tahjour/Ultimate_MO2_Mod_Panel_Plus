"""
Хранилище коллекции модов.
Поддерживает древовидную структуру: папки (группы) и моды.
Формат JSON:
{
    "version": 1,
    "tree": [
        {
            "type": "folder",
            "name": "My Favorites",
            "expanded": true,
            "children": [
                {
                    "type": "mod",
                    "uniqueId": "skyrimspecialedition_12345",
                    "modId": "12345",
                    "game": "skyrimspecialedition",
                    "title": "Some Mod",
                    "image": "https://...",
                    "url": "https://...",
                    "timestamp": 1234567890,
                    "status": "not_installed",
                    "notes": ""
                }
            ]
        },
        {
            "type": "mod",
            ...
        }
    ]
}
"""

import json
import shutil
import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal


class CollectionStorage(QObject):
    """
    Потокобезопасное хранилище коллекции.
    Испускает разные сигналы для разных типов изменений.
    """

    # Сигнал полной перезагрузки (структурные изменения: добавление/удаление папок)
    collection_changed = pyqtSignal()

    # Сигнал добавления новых модов (только добавление в корень, без перестроения)
    mods_added = pyqtSignal(list)  # список добавленных mod_node dict'ов

    # Сигнал обновления данных мода (описание, статус и т.д.)
    mod_updated = pyqtSignal(str, dict)  # uniqueId, обновлённые поля

    def __init__(self, filepath: Path):
        super().__init__()
        self._filepath = filepath
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"version": 1, "tree": []}
        self._load()

    # ──────────────────── File I/O ────────────────────

    def _load(self):
        if self._filepath.exists():
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # Миграция старых данных
                if "api_key" not in self._data:
                    self._data["api_key"] = ""
                if "font_size" not in self._data:
                    self._data["font_size"] = 12
                if "geometry" not in self._data:
                    self._data["geometry"] = ""
            except (json.JSONDecodeError, IOError):
                # Бэкап повреждённого файла
                backup = self._filepath.with_suffix(".json.bak")
                try:
                    shutil.copy2(self._filepath, backup)
                except Exception:
                    pass
                self._data = {
                    "version": 1,
                    "tree": [],
                    "api_key": "",
                    "font_size": 12,
                    "geometry": "",
                }

    def get_geometry(self) -> str:
        """Возвращает сохраненную геометрию окна (hex-строка)."""
        with self._lock:
            return self._data.get("geometry", "")

    def set_geometry(self, geometry_hex: str):
        """Сохраняет геометрию окна."""
        with self._lock:
            self._data["geometry"] = geometry_hex
            self._save()

    def get_api_key(self) -> str:
        """Возвращает сохраненный Nexus API ключ."""
        with self._lock:
            return self._data.get("api_key", "")

    def set_api_key(self, key: str):
        """Сохраняет Nexus API ключ."""
        with self._lock:
            self._data["api_key"] = key.strip()
            self._save()

    def get_font_size(self) -> int:
        """Возвращает сохраненный размер шрифта для описания."""
        with self._lock:
            return self._data.get("font_size", 12)

    def set_font_size(self, size: int):
        """Сохраняет размер шрифта."""
        with self._lock:
            self._data["font_size"] = size
            self._save()

    def _save(self):
        # Атомарная запись через временный файл
        tmp_path = self._filepath.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self._filepath)
        except Exception:
            # Если не удалось записать временный файл — пишем напрямую
            try:
                with open(self._filepath, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    # ──────────────────── Public API ────────────────────

    def get_tree(self) -> list[dict]:
        with self._lock:
            return json.loads(json.dumps(self._data.get("tree", [])))

    def set_tree(self, tree: list[dict], emit_changed: bool = True):
        with self._lock:
            self._data["tree"] = tree
            self._save()
        if emit_changed:
            self.collection_changed.emit()

    def add_mod(self, mod_data: dict, parent_path: list[int] | None = None):
        """
        Добавляет мод в коллекцию.
        parent_path — список индексов для навигации к папке-родителю.
        Если None — добавляет в корень.
        """
        with self._lock:
            node = self._ensure_mod_node(mod_data)

            # Проверяем дубликаты
            if self._find_mod(node["uniqueId"]):
                return False

            target = self._data["tree"]
            if parent_path:
                for idx in parent_path:
                    if 0 <= idx < len(target) and target[idx]["type"] == "folder":
                        target = target[idx]["children"]
                    else:
                        break

            target.append(node)
            self._save()

        # Испускаем сигнал добавления (не перестраиваем дерево!)
        self.mods_added.emit([node])
        return True

    def add_mods_bulk(self, mods_list: list[dict]) -> int:
        """Массовое добавление модов (от расширения). Возвращает кол-во добавленных."""
        added = 0
        added_nodes = []
        with self._lock:
            for mod_data in mods_list:
                node = self._ensure_mod_node(mod_data)
                if not self._find_mod(node["uniqueId"]):
                    self._data["tree"].append(node)
                    added_nodes.append(node)
                    added += 1
            if added > 0:
                self._save()

        if added > 0:
            # Испускаем сигнал добавления новых модов (без перестроения дерева!)
            self.mods_added.emit(added_nodes)
        return added

    def remove_mod(self, unique_id: str) -> bool:
        with self._lock:
            removed = self._remove_from_list(self._data["tree"], unique_id)
            if removed:
                self._save()

        if removed:
            self.collection_changed.emit()
        return removed

    def add_folder(self, name: str, parent_path: list[int] | None = None):
        """Создаёт новую папку/группу."""
        folder_node = {
            "type": "folder",
            "name": name,
            "expanded": True,
            "children": [],
        }

        with self._lock:
            target = self._data["tree"]
            if parent_path:
                for idx in parent_path:
                    if 0 <= idx < len(target) and target[idx]["type"] == "folder":
                        target = target[idx]["children"]

            target.append(folder_node)
            self._save()

        self.collection_changed.emit()

    def update_mod_field(self, unique_id: str, fields: dict):
        """Обновляет произвольные поля мода и испускает точечный сигнал."""
        with self._lock:
            node = self._find_mod(unique_id)
            if node:
                # Если обновляем nexus_description, заменяем BBCode на HTML
                if "nexus_description" in fields:
                    fields["nexus_description"] = self._bbcode_to_html(fields["nexus_description"])
                
                node.update(fields)
                self._save()
                # Возвращаем копию обновлённого узла
                updated = dict(node)
            else:
                return

        self.mod_updated.emit(unique_id, updated)

    @staticmethod
    def _bbcode_to_html(text: str) -> str:
        """Простейшая конвертация BBCode в HTML для описаний Nexus."""
        import re
        if not text:
            return ""
        
        # Заменяем переносы строк
        text = text.replace("\n", "<br>")
        
        # Основные теги
        replacements = [
            (r"\[b\](.*?)\[/b\]", r"<b>\1</b>"),
            (r"\[i\](.*?)\[/i\]", r"<i>\1</i>"),
            (r"\[u\](.*?)\[/u\]", r"<u>\1</u>"),
            (r"\[s\](.*?)\[/s\]", r"<s>\1</s>"),
            (r"\[url=(.*?)\](.*?)\[/url\]", r'<a href="\1">\2</a>'),
            (r"\[url\](.*?)\[/url\]", r'<a href="\1">\1</a>'),
            (r"\[img\](.*?)\[/img\]", r'<img src="\1" width="100%">'),
            (r"\[quote\](.*?)\[/quote\]", r"<blockquote>\1</blockquote>"),
            (r"\[color=(.*?)\](.*?)\[/color\]", r'<span style="color:\1">\2</span>'),
            (r"\[size=(.*?)\](.*?)\[/size\]", r'<span style="font-size:\1pt">\2</span>'),
            (r"\[center\](.*?)\[/center\]", r'<div style="text-align:center">\1</div>'),
            (r"\[list\](.*?)\[/list\]", r"<ul>\1</ul>"),
            (r"\[\*\](.*?)<br>", r"<li>\1</li>"),
            (r"\[h1\](.*?)\[/h1\]", r"<h1>\1</h1>"),
            (r"\[h2\](.*?)\[/h2\]", r"<h2>\1</h2>"),
            (r"\[h3\](.*?)\[/h3\]", r"<h3>\1</h3>"),
        ]
        
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.DOTALL)
            
        return text

    def get_all_mods(self) -> list[dict]:
        """Возвращает список всех модов в коллекции."""
        with self._lock:
            result = []
            self._collect_mods(self._data.get("tree", []), result)
            return result

    def _collect_mods(self, items: list[dict], result: list[dict]):
        for it in items:
            if it.get("type") == "mod":
                result.append(it)
            elif it.get("type") == "folder" and "children" in it:
                self._collect_mods(it["children"], result)

    def update_mod_status(self, unique_id: str, status: str):
        """Обновляет статус мода (not_installed, downloading, installed, error)."""
        self.update_mod_field(unique_id, {"status": status})

    def update_mod_notes(self, unique_id: str, notes: str):
        self.update_mod_field(unique_id, {"notes": notes})

    def get_all_mod_ids(self) -> list[str]:
        """Возвращает все uniqueId модов в коллекции."""
        with self._lock:
            result = []
            self._collect_ids(self._data.get("tree", []), result)
            return result

    def get_mod(self, unique_id: str) -> dict | None:
        """Возвращает копию данных мода по uniqueId."""
        with self._lock:
            node = self._find_mod(unique_id)
            if node:
                return dict(node)
            return None

    # ──────────────────── Internal helpers ────────────────────

    @staticmethod
    def _ensure_mod_node(data: dict) -> dict:
        """Нормализует данные мода в узел дерева."""
        return {
            "type": "mod",
            "uniqueId": data.get("uniqueId", f"{data.get('game', 'unknown')}_{data.get('id', '0')}"),
            "modId": str(data.get("id", data.get("modId", "0"))),
            "game": data.get("game", "unknown"),
            "title": data.get("title", "Unknown Mod"),
            "image": data.get("image", ""),
            "url": data.get("url", ""),
            "timestamp": data.get("timestamp", 0),
            "status": data.get("status", "not_installed"),
            "notes": data.get("notes", ""),
            "nexus_description": data.get("nexus_description", ""),
            "version": data.get("version", ""),
            "author": data.get("author", ""),
            "category": data.get("category", ""),
            "summary": data.get("summary", ""),
        }

    def _find_mod(self, unique_id: str, tree: list | None = None) -> dict | None:
        """Рекурсивный поиск мода по uniqueId."""
        if tree is None:
            tree = self._data.get("tree", [])
        for node in tree:
            if node.get("type") == "mod" and node.get("uniqueId") == unique_id:
                return node
            elif node.get("type") == "folder":
                result = self._find_mod(unique_id, node.get("children", []))
                if result:
                    return result
        return None

    def _remove_from_list(self, tree: list, unique_id: str) -> bool:
        for i, node in enumerate(tree):
            if node.get("type") == "mod" and node.get("uniqueId") == unique_id:
                tree.pop(i)
                return True
            elif node.get("type") == "folder":
                if self._remove_from_list(node.get("children", []), unique_id):
                    return True
        return False

    def _collect_ids(self, tree: list, result: list):
        for node in tree:
            if node.get("type") == "mod":
                result.append(node["uniqueId"])
            elif node.get("type") == "folder":
                self._collect_ids(node.get("children", []), result)