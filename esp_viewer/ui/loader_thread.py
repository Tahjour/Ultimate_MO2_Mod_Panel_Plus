import logging
import os
from typing import Dict, List, Tuple, Union, Optional, Any

from PyQt6.QtCore import QThread, pyqtSignal as Signal

from esp_viewer.core.data_types import Group, Record, PluginFile
from esp_viewer.core.conflict_analyzer import ConflictAnalysisResult, analyze_conflicts_for_plugin
from esp_viewer.core.plugin_file import parse_plugin, create_lazy_index, parse_record_at_offset
from esp_viewer.core.localization import load_string_tables, StringTables
from esp_viewer.core.formid_resolver import FormIDResolver
from esp_viewer.formatting.record_formatter import StructuredSubrecordParser


logger = logging.getLogger(__name__)


def build_record_paths(plugin) -> Dict[Tuple[str, int], List[Group]]:
    return {} # Отключаем тяжелое построение путей, оно не используется в критических местах


class PluginLoaderThread(QThread):
    finished = Signal(object, object, object)
    error = Signal(str)

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        try:
            plugin = parse_plugin(self.path)
            record_paths = build_record_paths(plugin)
            conflicts: ConflictAnalysisResult | None = None
            try:
                conflicts = analyze_conflicts_for_plugin(plugin, os.path.dirname(self.path))
            except Exception:
                conflicts = None
            self.finished.emit(plugin, record_paths, conflicts)
        except Exception as exc:
            logger.exception(f"Failed to parse plugin {self.path}")
            self.error.emit(str(exc))


class RecordStructureLoaderThread(QThread):
    finished = Signal(list, list, list, int)
    error = Signal(str)

    def __init__(self, 
                 record: Record, 
                 chain_plugins: List[str], 
                 chain_paths: List[str], 
                 plugin_cache: Dict[str, PluginFile],
                 lazy_index_cache: Dict[str, Any],
                 current_plugin: Optional[PluginFile],
                 load_order: List[str] = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.record = record
        self.chain_plugins = chain_plugins
        self.chain_paths = chain_paths
        self.plugin_cache = plugin_cache
        self.lazy_index_cache = lazy_index_cache
        self.current_plugin = current_plugin
        self.load_order = load_order or []
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    def run(self) -> None:
        try:
            structure_trees = []
            value_maps = []
            plugins_used = []
            
            # Кэш для результатов парсинга по хешу содержимого
            hash_to_tree = {}
            hash_to_val_map = {}
            
            # Если путей нет, используем имена
            paths = self.chain_paths if self.chain_paths and len(self.chain_paths) == len(self.chain_plugins) else self.chain_plugins
            
            # Гарантируем, что текущий плагин есть в списке, если это просмотр одиночной записи без конфликтов
            # или если он почему-то выпал из анализа.
            effective_chain_plugins = list(self.chain_plugins)
            effective_chain_paths = list(self.chain_paths) if self.chain_paths else []
            
            if self.current_plugin:
                current_name = os.path.basename(self.current_plugin.path)
                if current_name not in effective_chain_plugins:
                    effective_chain_plugins.append(current_name)
                    if effective_chain_paths:
                        effective_chain_paths.append(self.current_plugin.path)

            # Сортируем цепочку в соответствии с Load Order, если он доступен
            if self.load_order:
                order_map = {name.lower(): i for i, name in enumerate(self.load_order)}
                
                # Создаем список пар (плагин, путь) для совместной сортировки
                plugin_path_pairs = []
                for i in range(len(effective_chain_plugins)):
                    p_name = effective_chain_plugins[i]
                    p_path = effective_chain_paths[i] if i < len(effective_chain_paths) else p_name
                    plugin_path_pairs.append((p_name, p_path))
                
                # Сортируем пары по индексу в load_order
                plugin_path_pairs.sort(key=lambda x: order_map.get(x[0].lower(), 9999))
                
                # Распаковываем обратно
                effective_chain_plugins = [p[0] for p in plugin_path_pairs]
                effective_chain_paths = [p[1] for p in plugin_path_pairs]
            
            final_paths = effective_chain_paths if effective_chain_paths and len(effective_chain_paths) == len(effective_chain_plugins) else effective_chain_plugins
            
            for i, load_path in enumerate(final_paths):
                if self._is_canceled:
                    return
                
                plugin = self._get_plugin(load_path)
                if plugin is None:
                    structure_trees.append([])
                    value_maps.append({})
                    plugins_used.append(effective_chain_plugins[i])
                    continue
                
                plugins_used.append(os.path.basename(plugin.path))
                
                matching_record = None
                
                # Если это текущий плагин и та самая запись, используем её напрямую
                if plugin == self.current_plugin and \
                   self.record.signature == self.record.signature and \
                   self.record.form_id == self.record.form_id:
                    matching_record = self.record
                
                if matching_record is None and (self.record.signature, self.record.form_id) in plugin.record_map:
                    matching_record = plugin.record_map[(self.record.signature, self.record.form_id)]
                elif plugin.lazy_index:
                    offset = plugin.lazy_index.record_offsets.get((self.record.signature, self.record.form_id))
                    if offset is not None:
                        try:
                            matching_record = parse_record_at_offset(
                                plugin.path, offset, plugin.header_size, plugin
                            )
                            plugin.record_map[(self.record.signature, self.record.form_id)] = matching_record
                        except Exception:
                            logger.exception(f"Failed to parse lazy record at offset {offset} in {plugin.path}")
                
                if matching_record is None:
                    structure_trees.append([])
                    value_maps.append({})
                    continue

                # Добавляем резорвер к записи для использования в анализе конфликтов
                if not hasattr(matching_record, "_resolver"):
                    matching_record._resolver = plugin.formid_resolver

                # ОПТИМИЗАЦИЯ: Сравнение по хешу
                record_hash = matching_record.get_content_hash()
                if record_hash in hash_to_tree:
                    # MainWindow._merge_structure_tree теперь сама копирует узлы при необходимости,
                    # поэтому здесь мы можем просто передать ссылку на закэшированное дерево.
                    structure_trees.append(hash_to_tree[record_hash])
                    value_maps.append(hash_to_val_map[record_hash])
                    continue

                parser = StructuredSubrecordParser(matching_record, plugin)
                nodes = list(parser.iter_nodes())
                if not nodes:
                    structure_trees.append([])
                    value_maps.append({})
                    continue
                
                tree = self._build_structure_tree(nodes)
                val_map = self._build_structure_value_map(nodes)
                
                # Сохраняем в кэш
                hash_to_tree[record_hash] = tree
                hash_to_val_map[record_hash] = val_map
                
                structure_trees.append(tree)
                value_maps.append(val_map)

            # Находим победителя (последний плагин, у которого есть запись)
            winner_index = -1
            for i in range(len(structure_trees) - 1, -1, -1):
                if structure_trees[i]:
                    winner_index = i
                    break
            
            if winner_index == -1:
                winner_index = len(plugins_used) - 1
            
            self.finished.emit(structure_trees, value_maps, plugins_used, winner_index)
            
        except Exception as e:
            logger.exception("Error in RecordStructureLoaderThread")
            self.error.emit(str(e))

    def _get_plugin(self, path: str) -> Optional[PluginFile]:
        if self.current_plugin:
            current_path = os.path.normpath(self.current_plugin.path).lower()
            norm_path = os.path.normpath(path).lower()
            if norm_path == current_path or os.path.basename(norm_path) == os.path.basename(current_path):
                return self.current_plugin

        cached = self.plugin_cache.get(path)
        if cached is not None:
            return cached

        actual_path = path
        if not os.path.isabs(path) or not os.path.exists(path):
            plugin_name = os.path.basename(path)
            alt_path = os.path.join(os.path.dirname(self.current_plugin.path), plugin_name)
            if os.path.exists(alt_path):
                actual_path = alt_path
            else:
                found = False
                for p in self.plugin_cache.values():
                    if os.path.basename(p.path).lower() == plugin_name.lower():
                        actual_path = p.path
                        found = True
                        break
                if not found:
                    return None

        # Проверяем кэш индексов
        lazy_index = self.lazy_index_cache.get(actual_path)
        if not lazy_index:
            try:
                lazy_index = create_lazy_index(actual_path)
                self.lazy_index_cache[actual_path] = lazy_index
            except Exception:
                return None

        strings = StringTables()
        if lazy_index.localized:
            try:
                strings = load_string_tables(actual_path)
            except Exception:
                pass

        plugin = PluginFile(
            path=actual_path,
            file_size=lazy_index.file_size,
            header_size=lazy_index.header_size,
            localized=lazy_index.localized,
            strings=strings,
            children=[],
            masters=lazy_index.masters,
            lazy_index=lazy_index
        )
        plugin.formid_resolver = FormIDResolver(plugin)
        self.plugin_cache[path] = plugin
        return plugin

    def _build_structure_tree(self, nodes: List[Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        counts: Dict[str, int] = {}
        for node in nodes:
            index = counts.get(node.name, 0)
            counts[node.name] = index + 1
            key = (node.name, index)
            result.append(
                {
                    "key": key,
                    "name": node.name,
                    "children": self._build_structure_tree(node.children),
                }
            )
        return result

    def _build_structure_value_map(self, nodes: List[Any], base_path: Tuple = ()) -> Dict[Tuple, str]:
        value_map = {}
        counts: Dict[str, int] = {}
        for node in nodes:
            index = counts.get(node.name, 0)
            counts[node.name] = index + 1
            key = (node.name, index)
            path = base_path + (key,)
            value_map[path] = node.value
            value_map.update(self._build_structure_value_map(node.children, path))
        return value_map
