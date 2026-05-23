import logging
import struct
import mmap
import os
from typing import List, Optional, Tuple, Union, Iterator

from esp_viewer.core.data_types import Group, PluginFile, Record, LazyPluginIndex
from esp_viewer.core.group_parser import parse_group
from esp_viewer.core.load_order import build_load_order_info
from esp_viewer.core.formid_resolver import FormIDResolver
from esp_viewer.core.localization import StringTables, decode_text, load_string_tables
from esp_viewer.core.record_parser import is_valid_signature, parse_record
from esp_viewer.utils.binary_reader import ByteReader


logger = logging.getLogger(__name__)


LOCALIZED_FLAG = 0x00000080
ESL_FLAG = 0x00000200


def detect_header_size(data: bytes) -> int:
    """Определяет размер заголовка записи (20 или 24 байта)."""
    if len(data) < 24:
        return 24

    if data[:4] != b"TES4":
        logger.warning("File doesn't start with TES4, assuming header size 24")
        return 24

    data_size = struct.unpack_from("<I", data, 4)[0]

    for candidate in (24, 20):
        next_pos = candidate + data_size
        if next_pos + 4 <= len(data) and is_valid_signature(data[next_pos : next_pos + 4]):
            return candidate

    return 24




def _detect_localized(data: bytes, header_size: int) -> bool:
    if len(data) < header_size or data[:4] != b"TES4":
        return False
    flags = struct.unpack_from("<I", data, 8)[0]
    return bool(flags & LOCALIZED_FLAG)


def _detect_esl_from_header(data: bytes, header_size: int) -> bool:
    if len(data) < header_size or data[:4] != b"TES4":
        return False
    flags = struct.unpack_from("<I", data, 8)[0]
    return bool(flags & ESL_FLAG)


def _extract_masters_from_tes4(children: List[Union[Group, Record]]) -> List[str]:
    for child in children:
        if isinstance(child, Record) and child.signature == "TES4":
            masters: List[str] = []
            for field_obj in child.fields:
                if field_obj.signature == "MAST":
                    text = decode_text(field_obj.raw)
                    if text:
                        masters.append(text)
            return masters
    return []


def _detect_esl_from_tes4(children: List[Union[Group, Record]]) -> bool:
    for child in children:
        if isinstance(child, Record) and child.signature == "TES4":
            return bool(child.flags & ESL_FLAG)
    return False


def scan_record_headers(path: str) -> Iterator[Tuple[str, int, int, bool, List[str], bool]]:
    """
    Сверхбыстрое сканирование заголовков записей плагина.
    Возвращает: (signature, form_id, flags, is_deleted, masters, is_esl)
    """
    if not os.path.exists(path):
        return

    try:
        with open(path, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # Определяем размер заголовка по TES4
                if len(mm) < 24:
                    return
                
                header_size = 24
                # Простейшая логика определения header_size как в detect_header_size
                data_size = struct.unpack_from("<I", mm, 4)[0]
                for candidate in (24, 20):
                    next_pos = candidate + data_size
                    if next_pos + 4 <= len(mm):
                        sig = mm[next_pos:next_pos+4]
                        if sig.isalnum(): # Упрощенная проверка валидности
                            header_size = candidate
                            break

                pos = 0
                masters = []
                is_esl = False
                while pos + header_size <= len(mm):
                    sig_bytes = mm[pos:pos+4]
                    try:
                        sig = sig_bytes.decode('ascii', errors='ignore')
                    except:
                        break
                    
                    if sig == "GRUP":
                        # Заголовок группы 24 байта, просто переходим к следующей записи внутри неё
                        pos += 24
                        continue
                    
                    # Проверка на валидность сигнатуры (4 байта: заглавные, цифры или подчеркивание)
                    # Исключаем GRUP, так как он обработан выше
                    if len(sig) != 4 or not all(c.isupper() or c.isdigit() or c == '_' for c in sig):
                        pos += 1
                        continue
                    
                    # ВАЖНО: Мы нашли сигнатуру. Теперь нужно проверить, не является ли это
                    # случайным совпадением байт. В Bethesda-файлах за сигнатурой идет размер (4 байта).
                    # Мы уже имеем header_size (24 или 20).
                    try:
                        rec_data_size = struct.unpack_from("<I", mm, pos + 4)[0]
                    except:
                        pos += 1
                        continue
                        
                    # Если размер подозрительно велик (больше файла), это не запись
                    if pos + header_size + rec_data_size > len(mm):
                        pos += 1
                        continue
                    
                    # Если следующая за данными сигнатура тоже валидна (или это конец файла),
                    # то с высокой вероятностью мы на правильном пути.
                    next_sig_pos = pos + header_size + rec_data_size
                    if next_sig_pos < len(mm):
                        next_sig = mm[next_sig_pos:next_sig_pos+4]
                        # Проверка на валидность следующей сигнатуры (GRUP или Record)
                        is_next_valid = next_sig == b"GRUP" or (
                            len(next_sig) == 4 and 
                            all(65 <= b <= 90 or 48 <= b <= 57 or b == 95 for b in next_sig)
                        )
                        if not is_next_valid:
                            # Если следующая сигнатура не валидна, возможно это случайное попадание
                            # Но для TES4 (начала файла) мы делаем исключение
                            if sig != "TES4":
                                pos += 1
                                continue
                        
                    flags = struct.unpack_from("<I", mm, pos + 8)[0]
                    form_id = struct.unpack_from("<I", mm, pos + 12)[0]
                    is_deleted = bool(flags & 0x20)
                    
                    # Если это TES4, извлекаем MAST и ESL flag
                    if sig == "TES4":
                        masters = [] # Очищаем список при нахождении нового TES4
                        is_esl = bool(flags & 0x00000200)
                        data_pos = pos + header_size
                        end_pos = data_pos + rec_data_size
                        while data_pos + 6 <= end_pos:
                            f_sig = mm[data_pos:data_pos+4].decode('ascii', errors='ignore')
                            f_size = struct.unpack_from("<H", mm, data_pos + 4)[0]
                            if f_sig == "MAST":
                                mast_name = mm[data_pos+6 : data_pos+6+f_size].decode('ascii', errors='ignore').rstrip('\x00')
                                if mast_name:
                                    masters.append(mast_name)
                            data_pos += 6 + f_size
                    
                    yield sig, form_id, flags, is_deleted, masters, is_esl
                    
                    pos += header_size + rec_data_size
    except Exception as e:
        logger.error(f"Error scanning headers for {path}: {e}")
        return

def create_lazy_index(path: str) -> LazyPluginIndex:
    """Создает легкий индекс {(sig, formid): offset} через mmap-скан заголовков."""
    file_size = os.path.getsize(path)
    with open(path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            if len(mm) < 20:
                raise ValueError("File too small")
            
            header_size = detect_header_size(mm[:1024])
            localized = _detect_localized(mm[:1024], header_size)
            
            record_offsets = {}
            masters = []
            pos = 0
            
            while pos + header_size <= file_size:
                sig_bytes = mm[pos:pos+4]
                if sig_bytes == b"GRUP":
                    pos += 24 # Заголовок группы всегда 24
                    continue
                
                # Используем ту же надежную логику, что и в scan_record_headers
                try:
                    sig = sig_bytes.decode('ascii', errors='ignore')
                except:
                    pos += 1
                    continue

                if len(sig) == 4 and all(65 <= b <= 90 or 48 <= b <= 57 or b == 95 for b in sig_bytes):
                    try:
                        data_size = struct.unpack_from("<I", mm, pos + 4)[0]
                    except:
                        pos += 1
                        continue
                        
                    if pos + header_size + data_size > file_size:
                        pos += 1
                        continue

                    # Lookahead проверка
                    next_sig_pos = pos + header_size + data_size
                    if next_sig_pos < file_size:
                        next_sig = mm[next_sig_pos:next_sig_pos+4]
                        is_next_valid = next_sig == b"GRUP" or (
                            len(next_sig) == 4 and 
                            all(65 <= b <= 90 or 48 <= b <= 57 or b == 95 for b in next_sig)
                        )
                        if not is_next_valid and sig != "TES4":
                            pos += 1
                            continue
                    
                    form_id = struct.unpack_from("<I", mm, pos + 12)[0]
                    record_offsets[(sig, form_id)] = pos
                    
                    # Если это TES4, извлекаем MAST
                    if sig == "TES4":
                        data_pos = pos + header_size
                        end_pos = data_pos + data_size
                        while data_pos + 6 <= end_pos:
                            f_sig = mm[data_pos:data_pos+4]
                            f_size = struct.unpack_from("<H", mm, data_pos + 4)[0]
                            if f_sig == b"MAST":
                                try:
                                    mast_name = mm[data_pos+6 : data_pos+6+f_size].decode('ascii', errors='ignore').rstrip('\x00')
                                    if mast_name:
                                        masters.append(mast_name)
                                except:
                                    pass
                            data_pos += 6 + f_size
                    
                    pos += header_size + data_size
                else:
                    pos += 1

            return LazyPluginIndex(
                path=path,
                header_size=header_size,
                record_offsets=record_offsets,
                file_size=file_size,
                localized=localized,
                masters=masters
            )


def parse_record_at_offset(path: str, offset: int, header_size: int, plugin: Optional[PluginFile] = None) -> Record:
    """Парсит ровно одну запись по заданному смещению."""
    with open(path, "rb") as f:
        f.seek(offset)
        # Читаем заголовок
        header_data = f.read(header_size)
        if len(header_data) < header_size:
            raise ValueError("Unexpected EOF while reading record header")
        
        data_size = struct.unpack_from("<I", header_data, 4)[0]
        # Читаем данные записи
        record_data = f.read(data_size)
        if len(record_data) < data_size:
            raise ValueError("Unexpected EOF while reading record data")
        
        # Используем существующий parse_record, но нам нужен ByteReader
        from esp_viewer.utils.binary_reader import ByteReader
        # Объединяем для parse_record, так как он ожидает, что reader стоит в начале заголовка
        reader = ByteReader(header_data + record_data)
        return parse_record(reader, header_size, plugin)


def parse_plugin(path: str) -> PluginFile:
    with open(path, "rb") as handle:
        data = handle.read()

    header_size = detect_header_size(data)
    localized = _detect_localized(data, header_size)
    esl_from_header = _detect_esl_from_header(data, header_size)

    strings = StringTables()
    if localized:
        strings = load_string_tables(path)
        logger.info(f"Plugin is localized, loaded {strings.total_count} strings total")

    plugin = PluginFile(
        path=path,
        file_size=len(data),
        header_size=header_size,
        localized=localized,
        strings=strings,
        children=[],
        is_esl=path.lower().endswith(".esl") or esl_from_header,
    )

    reader = ByteReader(data)
    children: List[Union[Group, Record]] = []

    while reader.pos < reader.length:
        if not reader.can_read(4):
            break
        sig = reader.peek(4)
        if sig == b"GRUP":
            children.append(parse_group(reader, header_size, plugin))
        elif is_valid_signature(sig):
            children.append(parse_record(reader, header_size, plugin))
        else:
            logger.error(
                "Invalid top-level signature %r at offset %d, stopping",
                sig,
                reader.pos,
            )
            break

    plugin.children = children
    
    # Строим быстрый индекс рекордов
    record_map = {}
    
    def iter_records_local(nodes):
        for node in nodes:
            if isinstance(node, Record):
                yield node
            elif isinstance(node, Group):
                yield from iter_records_local(node.children)

    for rec in iter_records_local(children):
        record_map[(rec.signature, rec.form_id)] = rec
    plugin.record_map = record_map

    plugin.is_esl = plugin.is_esl or _detect_esl_from_tes4(children)
    plugin.masters = _extract_masters_from_tes4(children)
    plugin.load_order = build_load_order_info(path, plugin.masters)
    from esp_viewer.core.formid_resolver import FormIDResolver
    plugin.formid_resolver = FormIDResolver(plugin)
    return plugin
