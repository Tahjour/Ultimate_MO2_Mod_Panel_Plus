import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class LoadOrderInfo:
    masters: List[str]
    plugin_name: str

    def master_name(self, index: int) -> Optional[str]:
        if index < 0:
            return None
        if index < len(self.masters):
            return self.masters[index]
        if index == len(self.masters):
            return self.plugin_name
        return None

    def master_index(self, form_id: int) -> int:
        return (form_id >> 24) & 0xFF

    def local_id(self, form_id: int) -> int:
        return form_id & 0x00FFFFFF


def build_load_order_info(path: str, masters: List[str]) -> LoadOrderInfo:
    return LoadOrderInfo(masters=masters, plugin_name=os.path.basename(path))
