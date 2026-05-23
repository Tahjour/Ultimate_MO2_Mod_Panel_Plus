import os
from typing import Dict, List, Optional, Union

from .data_types import Group, PluginFile, Record


class FormIDResolver:
    """Двухпроходный индекс и форматирование FormID внутри одного плагина."""

    def __init__(self, plugin_or_path: Union[PluginFile, str], masters: Optional[List[str]] = None) -> None:
        if isinstance(plugin_or_path, PluginFile):
            self.plugin = plugin_or_path
            self.masters = plugin_or_path.masters
            self.plugin_name = os.path.basename(plugin_or_path.path)
            self.is_esl = plugin_or_path.is_esl
        else:
            self.plugin = None
            self.masters = masters or []
            self.plugin_name = os.path.basename(plugin_or_path)
            self.is_esl = self.plugin_name.lower().endswith(".esl")
        
        self.records_by_formid: Dict[int, Record] = {}
        if self.plugin:
            self._build_index()

    def master_name(self, index: int) -> Optional[str]:
        if index < 0:
            return None
        if index < len(self.masters):
            return self.masters[index]
        if index == len(self.masters):
            return self.plugin_name
        return None

    def _build_index(self) -> None:
        if not self.plugin:
            return
        # Используем уже готовый record_map из PluginFile
        for (sig, fid), rec in self.plugin.record_map.items():
            self.records_by_formid[fid] = rec

    def get(self, form_id: int) -> Optional[Record]:
        return self.records_by_formid.get(form_id)

    def format_formid(self, form_id: int, signature: Optional[str] = None) -> str:
        if form_id == 0xFFFFFFFF:
            return "None"
        if form_id == 0:
            return "00000000"
        hi = (form_id >> 24) & 0xFF
        display_formid = form_id
        if self.is_esl and hi == 0:
            local_id = form_id & 0x00FFFFFF
            display_formid = (0xFE << 24) | local_id
        hi = (display_formid >> 24) & 0xFF
        lo = display_formid & 0x00FFFFFF
        return f"[{hi:02X}:{lo:06X}]"

    def describe(self, form_id: int, signature: Optional[str] = None) -> str:
        base = self.format_formid(form_id, signature)
        target = self.get(form_id)
        if target is None:
            hi = (form_id >> 24) & 0xFF
            master = self.master_name(hi)
            if master:
                return f"{master} {base}"
            return base
        parts: List[str] = []
        if target.editor_id:
            parts.append(target.editor_id)
        if target.full_name and target.full_name != target.editor_id:
            parts.append(f'"{target.full_name}"')
        if not parts:
            return base
        return f"{' '.join(parts)} {base}"
