# cython: language_level=3
# distutils: language = c++

from typing import Dict, Tuple
from esp_viewer.core.enums import ConflictStatus

def _classify_fields_cython(
    dict record_fm,
    dict master_fm,
    dict winning_fm,
    bint is_master_pos,
    bint is_winning_pos,
    int chain_length,
) -> Dict[Tuple[str, int], ConflictStatus]:
    """
    Optimized version of _classify_fields using Cython.
    """
    if chain_length <= 1:
        return {}

    cdef dict status_map = {}
    # Creating a union of keys is still Python object manipulation
    cdef set keys = set(record_fm) | set(master_fm)
    cdef tuple key
    cdef object record_raw, master_raw, winning_raw

    for key in keys:
        if is_master_pos:
            status_map[key] = ConflictStatus.MASTER
            continue
        
        record_raw = record_fm.get(key)
        master_raw = master_fm.get(key)

        if record_raw == master_raw:
            status_map[key] = ConflictStatus.IDENTICAL_TO_MASTER
        elif is_winning_pos:
            status_map[key] = ConflictStatus.CONFLICT_CRITICAL
        else:
            # Safely get from winning_fm if it's not None
            winning_raw = winning_fm.get(key) if winning_fm is not None else None
            if record_raw == winning_raw:
                status_map[key] = ConflictStatus.OVERRIDE
            else:
                status_map[key] = ConflictStatus.CONFLICT_LOSES
            
    return status_map


def _field_map_cython(object record) -> dict:
    cdef dict index = {}
    cdef dict mapping = {}
    cdef list fields = record.fields
    cdef object field
    cdef str signature
    cdef int idx
    cdef bytes raw

    for field in fields:
        signature = field.signature
        idx = index.get(signature, 0)
        index[signature] = idx + 1
        mapping[(signature, idx)] = field.raw
    return mapping
