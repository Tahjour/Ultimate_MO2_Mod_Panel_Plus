from __future__ import annotations

import configparser
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Tuple

from esp_viewer.core.data_types import (
    PluginFile, 
    Record, 
    ConflictStatus, 
    RecordConflict, 
    ConflictAnalysisResult,
    LazyPluginIndex,
    Group
)
from esp_viewer.core.plugin_file import parse_plugin, scan_record_headers
from esp_viewer.core.search_engine import iter_records
from esp_viewer.core.formid_resolver import FormIDResolver

from esp_viewer.core.load_order import build_load_order_info, LoadOrderInfo
from esp_viewer.core.localization import decode_text

def _scan_plugin_worker(p_name: str, p_path: str, target_keys_set: set[Tuple[str, str, int]], masters: List[str]) -> List[Tuple[Tuple[str, str, int], str]]:
    """Воркер для параллельного сканирования одного плагина."""
    # Создаем временный резолвер для каноникализации
    resolver = FormIDResolver(p_path, masters)
    
    results = []
    is_esl_detected = False
    first_record = True
    
    for sig, form_id, flags, is_deleted, _, is_esl in scan_record_headers(p_path):
        if first_record:
            is_esl_detected = is_esl
            resolver.is_esl = is_esl
            first_record = False
            if sig == "TES4": continue
        
        # Пропускаем некритичные типы (как в эталоне)
        if sig in ("NAVI", "DOBJ", "LAND", "WNDW"):
            continue

        owner, local_id = _canonical_owner_fast(p_name, form_id, resolver)
        key = (sig, owner.lower(), local_id)
        
        if key in target_keys_set:
            results.append((key, p_name))
            
    return results

def _records_equal(rec1: Record, rec2: Record, resolver1: Optional[FormIDResolver], resolver2: Optional[FormIDResolver]) -> bool:
    """Глубокое сравнение записей с учетом канонических FormID."""
    if rec1.signature != rec2.signature:
        return False
    if rec1.flags != rec2.flags:
        return False
    if len(rec1.fields) != len(rec2.fields):
        return False
        
    for f1, f2 in zip(rec1.fields, rec2.fields):
        if f1.signature != f2.signature:
            return False
        if f1.size != f2.size:
            # TODO: Специфичная обработка для полей с FormID
            return False
        if f1.raw != f2.raw:
            # TODO: Формальное сравнение через resolver для FormID полей
            return False
            
    return True

def _is_benign_change(record: Record, master: Record) -> bool:
    """Определяет, является ли изменение 'безобидным' (как в xEdit)."""
    # Упрощенная логика: изменения в определенных полях (например, время) могут быть некритичными
    return False

def analyze_conflicts_for_plugin(target: PluginFile, directory: str) -> ConflictAnalysisResult:
    # 1. Получаем список путей к плагинам
    plugin_paths = _get_plugin_paths(directory, target)
    
    # 2. Быстро сканируем мастера для построения Load Order
    plugin_masters: Dict[str, List[str]] = {}
    path_by_name: Dict[str, str] = {}
    for path in plugin_paths:
        name = os.path.basename(path).lower()
        path_by_name[name] = path
        # Сканируем только до первого рекорда (TES4) для получения мастеров
        for sig, _, _, _, masters, is_esl in scan_record_headers(path):
            if sig == "TES4":
                plugin_masters[name] = masters
                break
        else:
            plugin_masters[name] = []

    # 3. Строим Load Order (упрощенно, по правилам Bethesda)
    load_order = _build_load_order_from_masters(plugin_masters, path_by_name)
    order_index = {name: idx for idx, name in enumerate(load_order)}
    
    # 4. Сканируем целевой плагин для получения target_ids
    target_name = os.path.basename(target.path).lower()
    target_ids: Dict[Tuple[str, str, int], Tuple[int, bool]] = {} # (sig, owner, local_id) -> (flags, is_deleted)
    
    # Для каноникализации нам нужен резолвер для каждого плагина
    resolvers: Dict[str, FormIDResolver] = {}
    
    def get_resolver(p_name: str, p_path: str) -> FormIDResolver:
        if p_name not in resolvers:
            p_masters = plugin_masters.get(p_name, [])
            resolvers[p_name] = FormIDResolver(p_path, p_masters)
        return resolvers[p_name]

    target_resolver = get_resolver(target_name, target.path)
    
    # Запоминаем маппинг локальных ID сразу при первом проходе
    local_key_map: Dict[Tuple[str, str, int], int] = {}
    
    for sig, form_id, flags, is_deleted, masters, is_esl in scan_record_headers(target.path):
        if sig == "TES4": continue
        owner, local_id = _canonical_owner_fast(target_name, form_id, target_resolver)
        key = (sig, owner.lower(), local_id)
        target_ids[key] = (flags, is_deleted)
        local_key_map[key] = form_id

    # 5. Проход по Load Order для выявления конфликтов
    conflicts: Dict[Tuple[str, str, int], List[str]] = {key: [] for key in target_ids}
    winners: Dict[Tuple[str, str, int], str] = {}
    
    target_keys_set = set(target_ids.keys())
    
    # Собираем список плагинов для параллельного сканирования
    tasks = []
    for p_name in load_order:
        p_path = path_by_name.get(p_name)
        if not p_path: continue
        
        # ОПТИМИЗАЦИЯ: Пропускаем базовые мастер-файлы
        is_base_master = not plugin_masters.get(p_name)
        if is_base_master and p_name != target_name:
            # Если это базовый мастер, он может быть владельцем некоторых записей
            # но сам не содержит конфликтов (он и есть база).
            # Мы добавляем его в цепочку только если он является владельцем.
            for key in target_ids:
                if key[1] == p_name:
                    if p_name not in conflicts[key]:
                        conflicts[key].append(p_name)
            continue
        
        # Добавляем в очередь на параллельное сканирование
        tasks.append((p_name, p_path, target_keys_set, plugin_masters.get(p_name, [])))

    # Запускаем пул потоков
    if tasks:
        # Используем ThreadPoolExecutor для стабильности в среде MO2
        # Чтение через mmap в scan_record_headers позволяет эффективно 
        # параллелить I/O даже с учетом GIL.
        with ThreadPoolExecutor(max_workers=8) as executor:
            # Создаем словарь для сохранения порядка результатов
            future_to_name = {executor.submit(_scan_plugin_worker, *task): task[0] for task in tasks}
            
            # Собираем результаты в порядке Load Order
            for p_name in load_order:
                # 1. Сначала добавляем target_name, если он совпадает с текущим p_name
                if p_name == target_name:
                    for key in target_ids:
                        if target_name not in conflicts[key]:
                            conflicts[key].append(target_name)
                
                # 2. Находим future для этого плагина (если он не был пропущен как базовый мастер)
                matching_future = next((f for f, name in future_to_name.items() if name == p_name), None)
                
                if matching_future:
                    try:
                        for key, res_p_name in matching_future.result():
                            if key in conflicts:
                                if res_p_name not in conflicts[key]:
                                    conflicts[key].append(res_p_name)
                                winners[key] = res_p_name
                    except Exception as e:
                        print(f"Error in worker thread for {p_name}: {e}")

    # 6. Формируем результат
    statuses: Dict[Tuple[str, int], ConflictStatus] = {}
    details: Dict[Tuple[str, int], RecordConflict] = {}
    
    for key, chain_names in conflicts.items():
        if not chain_names: continue 
        
        sig, owner, local_id = key
        local_form_id = local_key_map.get(key)
        if local_form_id is None: continue
        
        target_key = (sig, local_form_id)
        
        winner_name = winners.get(key, target_name)
        is_target_winner = (winner_name == target_name)
        
        # Если в цепочке более 1 плагина, это конфликт
        if len(chain_names) > 1:
            # Считаем хеш контента победителя для сравнения ITM
            # (Для оптимизации: в реальном приложении лучше сравнивать хеши, 
            # но здесь мы пока полагаемся на длину цепочки)
            if is_target_winner:
                status = ConflictStatus.OVERRIDE 
            else:
                status = ConflictStatus.CONFLICT_LOSES
        else:
            # Если запись есть только в одном плагине (нашем), 
            # но её владелец - другой плагин, это тоже OVERRIDE (одиночный)
            if owner.lower() != target_name:
                status = ConflictStatus.OVERRIDE
            else:
                status = ConflictStatus.ONLY_ONE
            
        statuses[target_key] = status
        details[target_key] = RecordConflict(
            status=status,
            field_statuses={}, # Ленивая загрузка: заполним позже при просмотре
            winning_plugin=winner_name,
            chain_length=len(chain_names),
            is_deleted=target_ids[key][1],
            is_injected=False, # TODO: реализовать _is_injected_fast
            chain_plugins=tuple(chain_names),
            chain_paths=tuple(path_by_name.get(name) for name in chain_names),
        )

    return ConflictAnalysisResult(statuses=statuses, details=details, load_order=load_order)

def _canonical_owner_fast(plugin_name: str, form_id: int, resolver: Optional[FormIDResolver]) -> Tuple[str, int]:
    """Быстрая версия _canonical_owner, использующая кешированный resolver."""
    if form_id == 0:
        return (plugin_name, 0)
    
    hi = (form_id >> 24) & 0xFF
    local_id = form_id & 0x00FFFFFF
    
    # ESL handling: FE:XXX
    if hi == 0xFE:
        # В Bethesda-файлах внутри плагина ESL записи имеют hi=0
        # Но при обращении извне они могут приходить как 0xFE...
        # Однако scan_record_headers возвращает "сырой" FormID из файла.
        # Для ESL плагина записи внутри него имеют hi=0.
        if resolver and resolver.is_esl:
            return (plugin_name, local_id)
        return (plugin_name, local_id) # Фоллбек

    # Если hi == 0 и плагин ESL, то это его собственная запись
    if hi == 0 and resolver and resolver.is_esl:
        return (plugin_name, local_id)
        
    if resolver:
        master_name = resolver.master_name(hi)
        if master_name:
            return (master_name, local_id)
            
    return (plugin_name, local_id)

def _get_plugin_paths(directory: str, target: PluginFile) -> List[str]:
    directories = _discover_data_directories(target.path, directory)
    return _list_plugins_multi(directories)

def _build_load_order_from_masters(plugin_masters: Dict[str, List[str]], path_by_name: Dict[str, str]) -> List[str]:
    deps: Dict[str, set[str]] = {}
    for name, masters in plugin_masters.items():
        needed = {m.lower() for m in masters if m.lower() in plugin_masters}
        deps[name] = needed

    def priority(name: str) -> Tuple[int, int, float, str]:
        path = path_by_name[name]
        ext = os.path.splitext(path)[1].lower()
        is_esm = (ext == ".esm") 
        is_esl = (ext == ".esl")
        
        # Хардкод для базовых файлов игры, чтобы они всегда были первыми
        base_game_files = {
            "skyrim.esm": -100,
            "update.esm": -99,
            "dawnguard.esm": -98,
            "hearthfires.esm": -97,
            "dragonborn.esm": -96,
        }
        base_priority = base_game_files.get(name.lower(), 0)
        
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
            
        # Порядок: ESM -> ESL -> ESP, затем base_priority, затем mtime, затем имя
        return (0 if is_esm else (1 if is_esl else 2), base_priority, mtime, name)

    ready = sorted([name for name, req in deps.items() if not req], key=priority)
    result: List[str] = []

    while ready:
        name = ready.pop(0)
        result.append(name)
        for dep_name, reqs in deps.items():
            if name in reqs:
                reqs.remove(name)
                if not reqs and dep_name not in result and dep_name not in ready:
                    ready.append(dep_name)
        ready.sort(key=priority)

    remaining = [name for name in deps if name not in result]
    remaining.sort(key=priority)
    return result + remaining


def is_conflict_status(status: ConflictStatus) -> bool:
    return status in {
        ConflictStatus.CONFLICT_BENIGN,
        ConflictStatus.OVERRIDE,
        ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT,
        ConflictStatus.CONFLICT_LOSES,
        ConflictStatus.CONFLICT_CRITICAL,
    }


def is_winning_status(status: ConflictStatus) -> bool:
    return status in {
        ConflictStatus.CONFLICT_BENIGN,
        ConflictStatus.OVERRIDE,
        ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT,
        ConflictStatus.CONFLICT_CRITICAL,
    }


def is_losing_status(status: ConflictStatus) -> bool:
    return status == ConflictStatus.CONFLICT_LOSES


def _load_plugins(directory: str, target: PluginFile) -> List[PluginFile]:
    """
    Загружает плагины из всех релевантных директорий.

    Эталон: bsplugins FileConflictParser.cpp использует реальный список плагинов
    (PluginList) с учётом game Data, а не только директорию целевого файла.
    """
    plugins: List[PluginFile] = []
    target_name = os.path.basename(target.path).lower()

    directories = _discover_data_directories(target.path, directory)
    for path in _list_plugins_multi(directories):
        name = os.path.basename(path).lower()
        if name == target_name:
            plugins.append(target)
            continue
        try:
            plugins.append(parse_plugin(path))
        except Exception:
            continue

    if not any(os.path.basename(p.path).lower() == target_name for p in plugins):
        plugins.append(target)
    return plugins


def _discover_data_directories(plugin_path: str, directory: Optional[str]) -> List[str]:
    """
    Собирает список директорий, где могут находиться плагины:
    - директория целевого плагина;
    - явная директория, переданная в analyze_conflicts_for_plugin;
    - директории из переменных окружения;
    - Data игры, обнаруженная через структуру MO2/МО3 (ModOrganizer.ini);
    - Data, найденная подъёмом вверх по дереву.
    """
    directories: List[str] = []

    # 1. Директория целевого плагина.
    plugin_dir = os.path.dirname(os.path.abspath(plugin_path))
    directories.append(plugin_dir)

    # 2. Явно переданный каталог.
    if directory and os.path.isdir(directory):
        directories.append(directory)

    # 3. Переменные окружения.
    env_vars = (
        "ESP_VIEWER_DATA_DIRS",
        "ESP_VIEWER_GAME_DATA",
        "SKYRIM_DATA_DIR",
        "SKYRIM_SE_DATA_DIR",
        "SKYRIMSE_DATA_DIR",
        "SKYRIM_DATA",
    )
    for key in env_vars:
        value = os.environ.get(key)
        if not value:
            continue
        if key == "ESP_VIEWER_DATA_DIRS":
            for part in value.split(";"):
                part = part.strip()
                if part and os.path.isdir(part):
                    directories.append(part)
        elif os.path.isdir(value):
            directories.append(value)

    # 4. Путь к Data игры через структуру MO2/MO3.
    mo_data = _detect_game_data_from_mo(plugin_dir)
    if mo_data and mo_data not in directories:
        directories.append(mo_data)

    # 5. Поиск Data при подъёме вверх по дереву.
    current = plugin_dir
    while True:
        parent = os.path.dirname(current)
        if parent == current:
            break
        if os.path.basename(current).lower() == "data" and os.path.isdir(current):
            if current not in directories:
                directories.append(current)
            break
        current = parent

    # Дедупликация.
    seen: set[str] = set()
    unique: List[str] = []
    for d in directories:
        norm = os.path.normcase(os.path.normpath(d))
        if norm not in seen:
            seen.add(norm)
            unique.append(d)
    return unique


def _read_game_data_from_mo_ini(ini_path: str) -> Optional[str]:
    parser = configparser.ConfigParser()
    try:
        parser.read(ini_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return None

    game_path = ""
    if parser.has_option("General", "gamePath"):
        game_path = parser.get("General", "gamePath", fallback="")
    game_path = game_path.strip()
    if not game_path:
        return None

    # MO2 может сохранять путь как @ByteArray(...)
    if game_path.startswith("@ByteArray(") and game_path.endswith(")"):
        game_path = game_path[len("@ByteArray(") : -1]

    # Исправляем путь, если он содержит слэши в стиле Qt или двойные слэши
    game_path = os.path.normpath(game_path)
    
    data_dir = os.path.join(game_path, "Data")
    if os.path.isdir(data_dir):
        return data_dir
    return None

def _detect_game_data_from_mo(plugin_dir: str) -> Optional[str]:
    """Пытается найти Data игры через ModOrganizer.ini."""
    # Поднимаемся вверх до корня MO
    current = os.path.abspath(plugin_dir)
    for _ in range(6):
        mo_ini = os.path.join(current, "ModOrganizer.ini")
        if os.path.isfile(mo_ini):
            return _read_game_data_from_mo_ini(mo_ini)
        
        # Проверяем также на уровень выше, если мы в папке mods
        if os.path.basename(current).lower() == "mods":
            mo_root = os.path.dirname(current)
            mo_ini_alt = os.path.join(mo_root, "ModOrganizer.ini")
            if os.path.isfile(mo_ini_alt):
                return _read_game_data_from_mo_ini(mo_ini_alt)

        parent = os.path.dirname(current)
        if parent == current: break
        current = parent
    return None

def _list_plugins_multi(directories: List[str]) -> List[str]:
    """
    Сканирует несколько директорий на наличие плагинов, избегая дубликатов по имени.
    """
    seen: Dict[str, str] = {}
    for directory in directories:
        if not directory or not os.path.isdir(directory):
            continue
        try:
            for name in os.listdir(directory):
                lower = name.lower()
                if lower.endswith((".esp", ".esm", ".esl")):
                    if lower not in seen:
                        seen[lower] = os.path.join(directory, name)
        except OSError:
            continue

    entries = list(seen.values())
    entries.sort()
    return entries


def _build_load_order(plugins: Iterable[PluginFile]) -> List[str]:
    by_name: Dict[str, PluginFile] = {
        os.path.basename(p.path).lower(): p for p in plugins
    }
    deps: Dict[str, set[str]] = {}
    for name, plugin in by_name.items():
        needed = {m.lower() for m in plugin.masters if m.lower() in by_name}
        deps[name] = needed

    def priority(name: str) -> Tuple[int, int, int, str]:
        plugin = by_name[name]
        ext = os.path.splitext(plugin.path)[1].lower()
        is_master = _is_master_plugin(plugin) or ext == ".esm"
        return (0 if is_master else 1, 0 if ext == ".esm" else 1, 0 if plugin.is_esl else 1, name)

    ready = sorted([name for name, req in deps.items() if not req], key=priority)
    result: List[str] = []

    while ready:
        name = ready.pop(0)
        result.append(name)
        for dep_name, reqs in deps.items():
            if name in reqs:
                reqs.remove(name)
                if not reqs and dep_name not in result and dep_name not in ready:
                    ready.append(dep_name)
        ready.sort(key=priority)

    remaining = [name for name in deps if name not in result]
    remaining.sort(key=priority)
    result.extend(remaining)
    return result


def _is_master_plugin(plugin: PluginFile) -> bool:
    for node in plugin.children:
        if isinstance(node, Record) and node.signature == "TES4":
            return bool(node.flags & 0x1)
    return False


def _canonical_owner(plugin: PluginFile, form_id: int) -> Tuple[str, int]:
    if form_id == 0:
        return (os.path.basename(plugin.path), 0)
    hi = (form_id >> 24) & 0xFF
    local_id = form_id & 0x00FFFFFF
    if plugin.is_esl and hi == 0:
        return (os.path.basename(plugin.path), local_id)
    if plugin.load_order is not None:
        master_name = plugin.load_order.master_name(hi)
        if master_name:
            return (master_name, local_id)
    return (os.path.basename(plugin.path), local_id)


def _is_injected(plugin: PluginFile, form_id: int) -> bool:
    hi = (form_id >> 24) & 0xFF
    if plugin.is_esl and hi == 0:
        return False
    if plugin.load_order is None:
        return False
    master_name = plugin.load_order.master_name(hi)
    return master_name is None


def _classify_record(
    record: Record,
    master: Record,
    winning: Record,
    chain: List[Tuple[PluginFile, Record]],
) -> ConflictStatus:
    if len(chain) == 1:
        return ConflictStatus.ONLY_ONE
    if record is master:
        return ConflictStatus.MASTER
        
    # Получаем резорверы для логического сравнения
    resolver_rec = getattr(record, "_resolver", None)
    resolver_master = getattr(master, "_resolver", None)
    resolver_winning = getattr(winning, "_resolver", None)
    
    same_as_master = _records_equal(record, master, resolver_rec, resolver_master)
    if same_as_master:
        if record is winning:
            # Проверяем, есть ли в цепочке записи, отличные от мастера
            has_conflicts = False
            for _, r in chain[1:]:
                res_r = getattr(r, "_resolver", None)
                if not _records_equal(r, master, res_r, resolver_master):
                    has_conflicts = True
                    break
            if has_conflicts:
                return ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT
        return ConflictStatus.IDENTICAL_TO_MASTER
        
    if _is_benign_change(record, master):
        return ConflictStatus.CONFLICT_BENIGN
        
    if record is winning:
        has_conflicts = False
        for _, r in chain[:-1]:
            res_r = getattr(r, "_resolver", None)
            if not _records_equal(r, record, res_r, resolver_rec):
                has_conflicts = True
                break
        if has_conflicts:
            return ConflictStatus.CONFLICT_CRITICAL
        return ConflictStatus.OVERRIDE
        
    if _records_equal(record, winning, resolver_rec, resolver_winning):
        return ConflictStatus.OVERRIDE
        
    return ConflictStatus.CONFLICT_LOSES


def _classify_fields(
    record: Record,
    master: Record,
    winning: Record,
    chain: List[Tuple[PluginFile, Record]],
) -> Dict[Tuple[str, int], ConflictStatus]:
    if len(chain) == 1:
        return {}
        
    # Получаем резорверы
    resolver_rec = getattr(record, "_resolver", None)
    resolver_master = getattr(master, "_resolver", None)
    resolver_winning = getattr(winning, "_resolver", None)
    
    record_fields = _field_map(record)
    master_fields = _field_map(master)
    winning_fields = _field_map(winning)
    
    keys = set(record_fields) | set(master_fields)
    status_map: Dict[Tuple[str, int, str], ConflictStatus] = {}
    
    for key in keys:
        if record is master:
            status_map[key] = ConflictStatus.MASTER
            continue
            
        record_raw = record_fields.get(key)
        master_raw = master_fields.get(key)
        winning_raw = winning_fields.get(key)
        
        # Логическое сравнение полей (упрощенное)
        sig = key[0]
        
        # Функция для умного сравнения двух raw значений поля
        def fields_equal(raw1, raw2, res1, res2):
            if raw1 == raw2: return True
            if raw1 is None or raw2 is None: return False
            if len(raw1) == 4 and sig not in ("EDID", "FULL", "TX00"):
                val1 = int.from_bytes(raw1, "little")
                val2 = int.from_bytes(raw2, "little")
                owner1, loc1 = _canonical_owner_fast(res1.plugin_name if res1 else "", val1, res1)
                owner2, loc2 = _canonical_owner_fast(res2.plugin_name if res2 else "", val2, res2)
                return owner1 == owner2 and loc1 == loc2
            return False

        if fields_equal(record_raw, master_raw, resolver_rec, resolver_master):
            status_map[key] = ConflictStatus.IDENTICAL_TO_MASTER
            continue
            
        if record is winning:
            status_map[key] = ConflictStatus.CONFLICT_CRITICAL
            continue
            
        if fields_equal(record_raw, winning_raw, resolver_rec, resolver_winning):
            status_map[key] = ConflictStatus.OVERRIDE
            continue
            
        status_map[key] = ConflictStatus.CONFLICT_LOSES
    return status_map
    return status_map


def _records_equal(a: Record, b: Record, resolver_a: Optional[FormIDResolver] = None, resolver_b: Optional[FormIDResolver] = None) -> bool:
    """Сравнивает две записи логически, учитывая ремаппинг FormID."""
    if a.signature != b.signature:
        return False
    
    # Если резорверы не переданы, используем побайтовое сравнение (старый метод)
    if not resolver_a or not resolver_b:
        return _field_map(a) == _field_map(b)
        
    map_a = _field_map(a)
    map_b = _field_map(b)
    
    if len(map_a) != len(map_b):
        return False
        
    for key, raw_a in map_a.items():
        raw_b = map_b.get(key)
        if raw_b is None:
            return False
            
        # Если байты идентичны - поля равны
        if raw_a == raw_b:
            continue
            
        # Если байты разные, проверяем, не FormID ли это
        # Для этого нужно знать структуру поля. 
        # Пока используем эвристику: если длина 4 и это не сигнатура, пробуем ремаппинг.
        sig = key[0]
        if len(raw_a) == 4 and sig not in ("EDID", "FULL", "TX00"):
            val_a = int.from_bytes(raw_a, "little")
            val_b = int.from_bytes(raw_b, "little")
            
            # Ремаппинг в канонический вид (OwnerPlugin, LocalID)
            owner_a, local_a = _canonical_owner_fast(resolver_a.plugin_name, val_a, resolver_a)
            owner_b, local_b = _canonical_owner_fast(resolver_b.plugin_name, val_b, resolver_b)
            
            if owner_a == owner_b and local_a == local_b:
                continue
                
        return False
        
    return True


def _field_map(record: Record) -> Dict[Tuple[str, int, str], bytes]:
    """Строит карту полей с учетом их содержимого для стабильных ключей."""
    index: Dict[str, int] = {}
    mapping: Dict[Tuple[str, int, str], bytes] = {}
    
    # Список сигнатур, которые могут использоваться как ключи (первые 4-8 байт)
    key_signatures = {"EDID", "FULL", "MAST", "SCRP", "CNAM"}
    
    for field in record.fields:
        sig = field.signature
        idx = index.get(sig, 0)
        index[sig] = idx + 1
        
        # Для полей-идентификаторов добавляем часть данных в ключ для стабильности при вставках
        extra_key = ""
        if sig in key_signatures and len(field.raw) >= 4:
            # Используем первые 8 байт (или меньше) как часть ключа
            extra_key = field.raw[:8].hex()
            
        mapping[(sig, idx, extra_key)] = field.raw
    return mapping


def _is_benign_change(record: Record, master: Record) -> bool:
    if record.signature != "TES4":
        return False
    diff = _diff_signatures(record, master)
    if not diff:
        return False
    return diff.issubset({"HEDR", "CNAM", "SNAM", "MAST", "DATA", "ONAM"})


def _diff_signatures(a: Record, b: Record) -> set[str]:
    map_a = _field_map(a)
    map_b = _field_map(b)
    diff: set[str] = set()
    for key in set(map_a) | set(map_b):
        if map_a.get(key) != map_b.get(key):
            diff.add(key[0])
    return diff
