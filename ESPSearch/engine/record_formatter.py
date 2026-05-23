import logging
import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .constants2 import MAX_FIELD_PREVIEW_BYTES, SUBRECORD_LABELS, BipedObjectFlag, ArmorType
from .data_types import Field, PluginFile, Record
from .localization import LOCALIZED_SIGNATURES, decode_text, resolve_string
from .value_formatter import format_flags


@dataclass
class DetailNode:
    name: str
    value: str
    refs: List[Tuple[Optional[str], int]] = field(default_factory=list)
    children: List["DetailNode"] = field(default_factory=list)


class StructuredSubrecordParser:
    def __init__(self, record: Record, plugin: Optional[PluginFile]) -> None:
        self.record = record
        self.plugin = plugin
        self._logger = logging.getLogger(__name__)
        self._text_signatures = {
            "MODL",
            "MOD2",
            "MOD3",
            "MOD4",
            "MOD5",
            "ICON",
            "MICO",
            "NAM1",
            "NAM2",
            "ALID",
            "ATKE",
            "UNAM",
            "TINT",
        }
        self._known_field_signatures = set(SUBRECORD_LABELS.keys())
        self._known_field_signatures.update(self._text_signatures)
        self._known_field_signatures.update(
            {
                "MODT",
                "KWDA",
                "MAST",
                "ONAM",
                "TNAM",
                "VMAD",
                "ACBS",
                "DATA",
                "DNAM",
                "SNDD",
                "MDOB",
                "BOD2",
                "BODT",
                "CNAM",
                "RNAM",
                "ANAM",
                "NAM2",
            }
        )
        self._context_labels = {
            ("WEAP", "DATA"): "DATA - Game Data",
            ("ARMO", "DATA"): "DATA - Data",
            ("BOOK", "DATA"): "DATA - Data",
            ("ARMO", "DNAM"): "DNAM - Armor Rating",
            ("WEAP", "CRDT"): "CRDT - Critical Data",
            ("ARMO", "BOD2"): "BOD2 - Biped Body Template",
            ("ARMA", "BODT"): "BODT - Biped Body Template",
            ("ARMA", "BOD2"): "BOD2 - Biped Body Template",
            ("RACE", "BOD2"): "BOD2 - Biped Body Template",
            ("RACE", "BODT"): "BODT - Biped Body Template",
            ("INFO", "RNAM"): "RNAM - Response Number",
            ("PACK", "CNAM"): "CNAM - Sound Category",
            ("PACK", "ANAM"): "ANAM - Sound Attenuation",
            ("HAZD", "NAM2"): "NAM2 - Hazard Data",
        }
        self._biped_slot_names = {
            0: "30: Head",
            1: "31: Hair",
            2: "32: Body",
            3: "33: Hands",
            4: "34: Forearms",
            5: "35: Amulet",
            6: "36: Ring",
            7: "37: Feet",
            8: "38: Calves",
            9: "39: Shield",
            10: "40: Tail",
            11: "41: Long Hair",
            12: "42: Circlet",
            13: "43: Ears",
            14: "44: Face Mouth",
            15: "45: Face Eyes",
            16: "46: Unnamed",
            17: "47: Unnamed",
            18: "48: Unnamed",
            19: "49: Unnamed",
            20: "50: Unnamed",
            21: "51: Unnamed",
            22: "52: Unnamed",
            23: "53: Unnamed",
            24: "54: Unnamed",
            25: "55: Unnamed",
            26: "56: Unnamed",
            27: "57: Unnamed",
            28: "58: Unnamed",
            29: "59: Unnamed",
            30: "60: FX01",
            31: "61: Unnamed",
        }
        self._run_on_names: Dict[int, str] = {
            0: "Subject",
            1: "Target",
            2: "Reference",
            3: "Combat Target",
            4: "Linked Reference",
            5: "Quest Alias",
            6: "Package Data",
            7: "Event Data",
        }
        self._perk_effect_types: Dict[int, str] = {
            0: "Quest + Stage",
            1: "Ability",
            2: "Entry Point",
        }
        self._perk_function_types: Dict[int, str] = {
            0: "Unknown 0",
            1: "Set Value",
            2: "Add Value",
            3: "Multiply Value",
            4: "Add Range To Value",
            5: "Add Actor Value Mult",
            6: "Absolute Value",
            7: "Negative Absolute Value",
            8: "Add Leveled List",
            9: "Add Activate Choice",
            10: "Select Spell",
            11: "Select Text",
            12: "Set to Actor Value Mult",
            13: "Multiply Actor Value Mult",
            14: "Multiply 1 + Actor Value Mult",
            15: "Set Text",
        }
        self._perk_epft_types: Dict[int, str] = {
            0: "None",
            1: "Float",
            2: "Float/AV,Float",
            3: "LVLI",
            4: "SPEL,lstring,flags",
            5: "SPEL",
            6: "string",
            7: "lstring",
        }

    def get_record_header_node(self) -> DetailNode:
        header = DetailNode("Record Header", "")
        header.children.append(DetailNode("Signature", self.record.signature))
        header.children.append(DetailNode("Data Size", f"{self.record.data_size} bytes"))
        header.children.append(DetailNode("Record Flags", format_flags(self.record.flags)))
        refs: List[Tuple[Optional[str], int]] = [(self.record.signature, self.record.form_id)]
        if self.plugin and self.plugin.formid_resolver:
            form_text = self.plugin.formid_resolver.format_formid(self.record.form_id, self.record.signature)
        else:
            form_text = f"0x{self.record.form_id:08X}"
        header.children.append(DetailNode("FormID", form_text, refs))
        header.children.append(DetailNode("Version Control Info 1", f"0x{self.record.vci1:08X}"))
        header.children.append(DetailNode("File Offset", f"0x{self.record.raw_offset:X}"))

        if self.record.form_version is not None:
            header.children.append(DetailNode("Form Version", str(self.record.form_version)))
        if self.record.vci2 is not None:
            header.children.append(DetailNode("Version Control Info 2", f"0x{self.record.vci2:04X}"))
        if self.record.is_compressed:
            header.children.append(DetailNode("Compression", "Yes (zlib)"))
        if self.record.parse_error:
            header.children.append(DetailNode("Parse Error", self.record.parse_error))

        if self.record.signature == "TES4" and self.record.form_id == 0 and self.plugin:
            header.children.append(DetailNode("Localized", "Yes" if self.plugin.localized else "No"))
            header.children.append(DetailNode("Record Header Size", str(self.plugin.header_size)))

        return header

    def _format_localized_or_text(self, field_obj: Field) -> Optional[str]:
        text = resolve_string(field_obj, self.plugin)
        if text:
            return text
        return None

    def _field_label(self, signature: str) -> str:
        if not signature:
            return "Unknown"
        override = self._context_labels.get((self.record.signature, signature))
        if override:
            return override
        label = SUBRECORD_LABELS.get(signature)
        if label:
            return f"{signature} - {label}"
        return signature

    def _is_known_field_signature(self, signature: str) -> bool:
        return signature in self._known_field_signatures

    def _format_formid_value(
        self,
        form_id: int,
        signature: Optional[str] = None,
    ) -> Tuple[str, List[Tuple[Optional[str], int]]]:
        refs = [(signature, form_id)]
        if self.plugin and self.plugin.formid_resolver:
            text = self.plugin.formid_resolver.describe(form_id, signature)
            return text, refs
        return f"0x{form_id:08X}", refs

    def _format_numeric(self, field_obj: Field) -> str:
        if field_obj.size == 0:
            return "Present"
        if field_obj.size in (1, 2, 4, 8):
            value = int.from_bytes(field_obj.raw, "little", signed=False)
            if value == 0:
                return ""
            return f"{value} (0x{value:0{field_obj.size * 2}X})"

        preview_size = min(field_obj.size, MAX_FIELD_PREVIEW_BYTES)
        hex_preview = field_obj.raw[:preview_size].hex(" ").upper()
        if field_obj.size > preview_size:
            return f"{hex_preview} ... ({field_obj.size} bytes total)"
        return hex_preview

    def _format_unknown_value(self, field_obj: Field) -> str:
        if field_obj.size == 0:
            return "Present"
        if field_obj.size <= 256:
            hex_preview = field_obj.raw.hex(" ").upper()
            return f"{hex_preview} ({field_obj.size} bytes)"
        return f"{field_obj.size} bytes"

    def _format_u32_chunk(self, chunk: bytes) -> str:
        value = int.from_bytes(chunk, "little", signed=False)
        try:
            float_val = struct.unpack("<f", chunk)[0]
            if -1e10 < float_val < 1e10 and float_val != 0.0:
                return f"{value} (0x{value:08X}, float: {float_val:.6g})"
        except struct.error:
            pass
        return f"{value} (0x{value:08X})"

    def _format_generic_formid_node(self, field_obj: Field) -> DetailNode:
        """Форматирует поле как FormID."""
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) != 4:
            return DetailNode(label, self._format_numeric(field_obj))
        
        value = int.from_bytes(raw, "little", signed=False)
        text, refs = self._format_formid_value(value)
        
        node = DetailNode(label, text, refs)
        issues: List[str] = []
        self._validate_formid(value, None, issues, label)
        self._attach_validation(node, issues)
        return node

    def _format_struct_array_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) % 4 != 0 or not raw:
            issues.append(f"Unexpected {field_obj.signature} size {len(raw)}")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        
        count = len(raw) // 4
        node.value = f"[{count}]"
        preview = min(count, 16)
        
        # Try to guess content type (FormID, Float, or Int)
        is_float = False
        is_formid = False
        
        # Heuristic for Float: many small values in range 0.001..1000 or very small
        # Heuristic for FormID: high bytes are usually 0x00, 0x01, 0xFE, or load order
        
        for i in range(preview):
            chunk = raw[i * 4 : (i + 1) * 4]
            val_u32 = int.from_bytes(chunk, "little", signed=False)
            val_f32 = struct.unpack_from("<f", chunk)[0]
            
            # FormID heuristic
            if 0 < val_u32 < 0xFFFFFFFF:
                # If it looks like a FormID (valid load order or high master)
                if self.plugin and self.plugin.formid_resolver:
                    if self.plugin.formid_resolver.get(val_u32) or self.plugin.formid_resolver.master_name(val_u32):
                        is_formid = True
            
            # Float heuristic (avoid NaNs and extremely large/small values unless they look like floats)
            if not is_formid and abs(val_f32) < 1e10 and abs(val_f32) > 1e-10:
                if not (val_u32 > 0x00FFFFFF and val_u32 < 0xFE000000): # Common int range
                     is_float = True

        for i in range(preview):
            chunk = raw[i * 4 : (i + 1) * 4]
            value = int.from_bytes(chunk, "little", signed=False)
            refs: List[Tuple[Optional[str], int]] = []
            
            if is_formid:
                text, refs = self._format_formid_value(value)
            elif is_float:
                val_f = struct.unpack_from("<f", chunk)[0]
                text = f"{val_f:.6g}"
            else:
                text = self._format_u32_chunk(chunk)

            entry = DetailNode(f"Entry {i}", text, refs)
            node.children.append(entry)
            
        if count > preview:
            node.children.append(DetailNode("More", f"+{count - preview} entries"))
        self._attach_validation(node, issues)
        return node

    def _format_ref_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) != 24:
            return DetailNode(label, self._format_numeric(field_obj))
        x, y, z, rx, ry, rz = struct.unpack_from("<6f", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Position X", f"{x:.6g}"))
        node.children.append(DetailNode("Position Y", f"{y:.6g}"))
        node.children.append(DetailNode("Position Z", f"{z:.6g}"))
        node.children.append(DetailNode("Rotation X", f"{rx:.6g}"))
        node.children.append(DetailNode("Rotation Y", f"{ry:.6g}"))
        node.children.append(DetailNode("Rotation Z", f"{rz:.6g}"))
        return node

    def _format_dial_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 4:
            return DetailNode(label, self._format_numeric(field_obj))
        unknown_flag = raw[0]
        tab = raw[1]
        subtype = raw[2]
        unused = raw[3]
        tab_names = {
            0: "Player Dialogue",
            1: "Favor Dialogue",
            2: "Scenes",
            3: "Combat",
            4: "Favors",
            5: "Detection",
            6: "Service",
            7: "Misc",
        }
        tab_name = tab_names.get(tab)
        tab_text = f"{tab} ({tab_name})" if tab_name else str(tab)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Unknown Flag", "Yes" if unknown_flag else "No"))
        node.children.append(DetailNode("Dialogue Tab", tab_text))
        node.children.append(DetailNode("Subtype ID", str(subtype)))
        node.children.append(DetailNode("Unused", str(unused)))
        return node

    def _format_info_trdt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 24:
            return DetailNode(label, self._format_numeric(field_obj))
        emotion_type = int.from_bytes(raw[0:4], "little", signed=False)
        emotion_value = int.from_bytes(raw[4:8], "little", signed=False)
        unknown = int.from_bytes(raw[8:12], "little", signed=True)
        response_id = raw[12]
        junk1 = raw[13:16].hex(" ").upper()
        sound_id = int.from_bytes(raw[16:20], "little", signed=False)
        use_emotion_anim = raw[20]
        junk2 = raw[21:24].hex(" ").upper()
        node = DetailNode(label, "")
        node.children.append(DetailNode("Emotion Type", str(emotion_type)))
        node.children.append(DetailNode("Emotion Value", str(emotion_value)))
        node.children.append(DetailNode("Unknown", str(unknown)))
        node.children.append(DetailNode("Response ID", str(response_id)))
        node.children.append(DetailNode("Junk 1", junk1))
        issues: List[str] = []
        if sound_id:
            sound_text, sound_refs = self._format_formid_value(sound_id, "SNDR")
            node.children.append(DetailNode("Sound File", sound_text, sound_refs))
            self._validate_formid(sound_id, "SNDR", issues, "Sound File")
        else:
            node.children.append(DetailNode("Sound File", "00000000"))
        node.children.append(DetailNode("Use Emotion Animation", "Yes" if use_emotion_anim else "No"))
        node.children.append(DetailNode("Junk 2", junk2))
        self._attach_validation(node, issues)
        return node

    def _format_xclc_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        x, y, flags = struct.unpack_from("<iiI", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Grid X", str(x)))
        node.children.append(DetailNode("Grid Y", str(y)))
        node.children.append(DetailNode("Flags", f"0x{flags:08X} ({flags})"))
        return node

    def _format_land_vnml_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) % 3 != 0:
            return DetailNode(label, self._format_numeric(field_obj))
        count = len(raw) // 3
        node = DetailNode(label, f"[{count}]")
        xs = raw[0::3]
        ys = raw[1::3]
        zs = raw[2::3]
        node.children.append(DetailNode("Grid", "33x33" if count == 1089 else f"{count} vectors"))
        node.children.append(DetailNode("X Range", f"{min(xs)}..{max(xs)}"))
        node.children.append(DetailNode("Y Range", f"{min(ys)}..{max(ys)}"))
        node.children.append(DetailNode("Z Range", f"{min(zs)}..{max(zs)}"))
        return node

    def _format_land_vclr_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) % 3 != 0:
            return DetailNode(label, self._format_numeric(field_obj))
        count = len(raw) // 3
        node = DetailNode(label, f"[{count}]")
        rs = raw[0::3]
        gs = raw[1::3]
        bs = raw[2::3]
        node.children.append(DetailNode("Grid", "33x33" if count == 1089 else f"{count} colors"))
        node.children.append(DetailNode("R Range", f"{min(rs)}..{max(rs)}"))
        node.children.append(DetailNode("G Range", f"{min(gs)}..{max(gs)}"))
        node.children.append(DetailNode("B Range", f"{min(bs)}..{max(bs)}"))
        return node

    def _format_land_vhgt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 4 + 1089:
            return DetailNode(label, self._format_numeric(field_obj))
        offset = struct.unpack_from("<f", raw, 0)[0]
        gradients = struct.unpack_from("<1089b", raw, 4)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Grid", "33x33"))
        node.children.append(DetailNode("Offset", f"{offset:.6g}"))
        node.children.append(DetailNode("Gradient Range", f"{min(gradients)}..{max(gradients)}"))
        return node

    def _format_land_vtxt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) % 8 != 0 or not raw:
            return DetailNode(label, self._format_numeric(field_obj))
        count = len(raw) // 8
        node = DetailNode(label, f"[{count}]")
        preview = min(count, 8)
        for i in range(preview):
            pos = i * 8
            position = int.from_bytes(raw[pos : pos + 2], "little", signed=False)
            opacity = struct.unpack_from("<f", raw, pos + 4)[0]
            node.children.append(DetailNode(f"Entry {i}", f"Pos {position}, Opacity {opacity:.6g}"))
        if count > preview:
            node.children.append(DetailNode("More", f"+{count - preview} entries"))
        return node

    def _format_xprm_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        if len(raw) < 32:
            issues.append(f"Unexpected XPRM size {len(raw)} (expected 32)")
            self._attach_validation(node, issues)
            return node
        bounds = struct.unpack_from("<3f", raw, 0)
        colors = struct.unpack_from("<3f", raw, 12)
        unknown_float = struct.unpack_from("<f", raw, 24)[0]
        primitive_type = struct.unpack_from("<I", raw, 28)[0]
        type_names = {
            1: "Box",
            2: "Sphere",
            3: "Portal Box",
            4: "Unknown",
        }
        type_name = type_names.get(primitive_type)
        type_text = f"{primitive_type} ({type_name})" if type_name else str(primitive_type)
        node.children.append(DetailNode("Bounds (X/Y/Z)", f"{bounds[0]:.6g}/{bounds[1]:.6g}/{bounds[2]:.6g}"))
        node.children.append(DetailNode("Color (R/G/B)", f"{colors[0]:.6g}/{colors[1]:.6g}/{colors[2]:.6g}"))
        node.children.append(DetailNode("Unknown Float", f"{unknown_float:.6g}"))
        node.children.append(DetailNode("Type", type_text))
        if len(raw) > 32:
            node.children.append(DetailNode("Trailing", f"{len(raw) - 32} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_xmbo_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        if len(raw) < 12:
            issues.append(f"Unexpected XMBO size {len(raw)} (expected 12)")
            self._attach_validation(node, issues)
            return node
        bounds = struct.unpack_from("<3f", raw, 0)
        node.children.append(DetailNode("Bounds (X/Y/Z)", f"{bounds[0]:.6g}/{bounds[1]:.6g}/{bounds[2]:.6g}"))
        if len(raw) > 12:
            node.children.append(DetailNode("Trailing", f"{len(raw) - 12} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_lvlo_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        if len(raw) < 12:
            issues.append(f"Unexpected LVLO size {len(raw)} (expected 12)")
            self._attach_validation(node, issues)
            return node
        level = int.from_bytes(raw[0:4], "little", signed=False)
        form_id = int.from_bytes(raw[4:8], "little", signed=False)
        count = int.from_bytes(raw[8:12], "little", signed=False)
        text, refs = self._format_formid_value(form_id)
        node.children.append(DetailNode("Level", str(level)))
        node.children.append(DetailNode("Item", text, refs))
        node.children.append(DetailNode("Count", str(count)))
        self._validate_formid(form_id, None, issues, "Item")
        if len(raw) > 12:
            node.children.append(DetailNode("Trailing", f"{len(raw) - 12} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_llct_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        if len(raw) < 1:
            issues.append(f"Unexpected LLCT size {len(raw)} (expected 1)")
            self._attach_validation(node, issues)
            return node
        count = int.from_bytes(raw[0:1], "little", signed=False)
        node.value = str(count)
        if len(raw) > 1:
            node.children.append(DetailNode("Trailing", f"{len(raw) - 1} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_ptda_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        if len(raw) < 12:
            issues.append(f"Unexpected PTDA size {len(raw)} (expected 12)")
            self._attach_validation(node, issues)
            return node
        target_type, target_value, count = struct.unpack_from("<iIi", raw, 0)
        type_names = {
            0: "Specific Reference",
            1: "Object ID",
            2: "Object Type",
            3: "Linked Reference",
            4: "Ref Alias",
            6: "Self",
        }
        type_name = type_names.get(target_type)
        type_text = f"{target_type} ({type_name})" if type_name else str(target_type)
        node.children.append(DetailNode("Type", type_text))
        if target_type in {0, 3}:
            text, refs = self._format_formid_value(target_value, "REFR")
            node.children.append(DetailNode("Target", text, refs))
            self._validate_formid(target_value, "REFR", issues, "Target")
        elif target_type == 1:
            text, refs = self._format_formid_value(target_value)
            node.children.append(DetailNode("Target", text, refs))
            self._validate_formid(target_value, None, issues, "Target")
        elif target_type == 2:
            node.children.append(DetailNode("Target Type", f"{target_value} (0x{target_value:08X})"))
        elif target_type == 4:
            node.children.append(DetailNode("Target Alias", str(target_value)))
        elif target_type == 6:
            node.children.append(DetailNode("Target", "Self"))
        else:
            node.children.append(DetailNode("Target", f"{target_value} (0x{target_value:08X})"))
        node.children.append(DetailNode("Count", str(count)))
        if len(raw) > 12:
            node.children.append(DetailNode("Trailing", f"{len(raw) - 12} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_nvmi_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        pos = 0

        def read_u32(name: str) -> Optional[int]:
            nonlocal pos
            if pos + 4 > len(raw):
                issues.append(f"{name}: unexpected end")
                return None
            value = int.from_bytes(raw[pos : pos + 4], "little", signed=False)
            pos += 4
            return value

        def read_f32(name: str) -> Optional[float]:
            nonlocal pos
            if pos + 4 > len(raw):
                issues.append(f"{name}: unexpected end")
                return None
            value = struct.unpack_from("<f", raw, pos)[0]
            pos += 4
            return value

        def read_u8(name: str) -> Optional[int]:
            nonlocal pos
            if pos + 1 > len(raw):
                issues.append(f"{name}: unexpected end")
                return None
            value = raw[pos]
            pos += 1
            return value

        navmesh_id = read_u32("Navmesh")
        if navmesh_id is None:
            self._attach_validation(node, issues)
            return node
        navmesh_text, navmesh_refs = self._format_formid_value(navmesh_id, "NAVM")
        node.children.append(DetailNode("Navmesh", navmesh_text, navmesh_refs))
        self._validate_formid(navmesh_id, "NAVM", issues, "Navmesh")

        flags = read_u32("Flags")
        if flags is None:
            self._attach_validation(node, issues)
            return node
        node.children.append(DetailNode("Flags", f"0x{flags:08X} ({flags})"))

        cx = read_f32("Center X")
        cy = read_f32("Center Y")
        cz = read_f32("Center Z")
        if cx is not None and cy is not None and cz is not None:
            node.children.append(DetailNode("Center (X/Y/Z)", f"{cx:.6g}/{cy:.6g}/{cz:.6g}"))

        preferred_flag = read_u32("Preferred Merges Flag")
        if preferred_flag is not None:
            node.children.append(DetailNode("Preferred Merges Flag", f"0x{preferred_flag:08X} ({preferred_flag})"))

        merged_count = read_u32("Merged To Count")
        if merged_count is not None:
            merged_node = DetailNode("Merged To", f"[{merged_count}]")
            preview = min(merged_count, 4)
            for i in range(preview):
                form_id = read_u32(f"Merged To {i}")
                if form_id is None:
                    break
                text, refs = self._format_formid_value(form_id, "NAVM")
                merged_node.children.append(DetailNode(f"Entry {i}", text, refs))
                self._validate_formid(form_id, "NAVM", issues, f"Merged To {i}")
            if merged_count > preview:
                merged_node.children.append(DetailNode("More", f"+{merged_count - preview} entries"))
                pos += (merged_count - preview) * 4
            node.children.append(merged_node)

        preferred_count = read_u32("Preferred Merges Count")
        if preferred_count is not None:
            pref_node = DetailNode("Preferred Merges", f"[{preferred_count}]")
            preview = min(preferred_count, 4)
            for i in range(preview):
                form_id = read_u32(f"Preferred Merge {i}")
                if form_id is None:
                    break
                text, refs = self._format_formid_value(form_id, "NAVM")
                pref_node.children.append(DetailNode(f"Entry {i}", text, refs))
                self._validate_formid(form_id, "NAVM", issues, f"Preferred Merge {i}")
            if preferred_count > preview:
                pref_node.children.append(DetailNode("More", f"+{preferred_count - preview} entries"))
                pos += (preferred_count - preview) * 4
            node.children.append(pref_node)

        door_count = read_u32("Linked Doors Count")
        if door_count is not None:
            doors_node = DetailNode("Linked Doors", f"[{door_count}]")
            preview = min(door_count, 3)
            for i in range(preview):
                unknown = read_u32(f"Door Unknown {i}")
                form_id = read_u32(f"Door Ref {i}")
                if unknown is None or form_id is None:
                    break
                text, refs = self._format_formid_value(form_id, "REFR")
                doors_node.children.append(DetailNode(f"Entry {i}", f"{unknown} / {text}", refs))
                self._validate_formid(form_id, "REFR", issues, f"Door {i}")
            if door_count > preview:
                doors_node.children.append(DetailNode("More", f"+{door_count - preview} entries"))
                pos += (door_count - preview) * 8
            node.children.append(doors_node)

        island_flag = read_u8("Is Island")
        if island_flag is not None:
            node.children.append(DetailNode("Is Island", "Yes" if island_flag else "No"))
            if island_flag:
                min_x = read_f32("Min X")
                min_y = read_f32("Min Y")
                min_z = read_f32("Min Z")
                max_x = read_f32("Max X")
                max_y = read_f32("Max Y")
                max_z = read_f32("Max Z")
                if None not in (min_x, min_y, min_z, max_x, max_y, max_z):
                    node.children.append(
                        DetailNode("Bounds Min", f"{min_x:.6g}/{min_y:.6g}/{min_z:.6g}")
                    )
                    node.children.append(
                        DetailNode("Bounds Max", f"{max_x:.6g}/{max_y:.6g}/{max_z:.6g}")
                    )
                tri_count = read_u32("Triangle Count")
                if tri_count is not None:
                    node.children.append(DetailNode("Triangle Count", str(tri_count)))
                    need = tri_count * 6
                    if pos + need > len(raw):
                        issues.append("Triangle data truncated")
                        self._attach_validation(node, issues)
                        return node
                    pos += need
                vert_count = read_u32("Vertex Count")
                if vert_count is not None:
                    node.children.append(DetailNode("Vertex Count", str(vert_count)))
                    need = vert_count * 12
                    if pos + need > len(raw):
                        issues.append("Vertex data truncated")
                        self._attach_validation(node, issues)
                        return node
                    pos += need

        location_marker = read_u32("Location Marker")
        if location_marker is not None:
            node.children.append(DetailNode("Location Marker", f"0x{location_marker:08X} ({location_marker})"))

        worldspace_id = read_u32("Worldspace")
        if worldspace_id is not None:
            world_text, world_refs = self._format_formid_value(worldspace_id, "WRLD")
            node.children.append(DetailNode("Worldspace", world_text, world_refs))
            if worldspace_id == 0x0000003C:
                if pos + 4 <= len(raw):
                    grid_y = int.from_bytes(raw[pos : pos + 2], "little", signed=True)
                    grid_x = int.from_bytes(raw[pos + 2 : pos + 4], "little", signed=True)
                    pos += 4
                    node.children.append(DetailNode("Grid (Y/X)", f"{grid_y}/{grid_x}"))
                else:
                    issues.append("Grid data truncated")
            else:
                cell_id = read_u32("Cell")
                if cell_id is not None:
                    cell_text, cell_refs = self._format_formid_value(cell_id, "CELL")
                    node.children.append(DetailNode("Cell", cell_text, cell_refs))

        if pos < len(raw):
            node.children.append(DetailNode("Remaining", f"{len(raw) - pos} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_nvnm_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"{len(raw)} bytes")
        issues: List[str] = []
        pos = 0

        def read_u32(name: str) -> Optional[int]:
            nonlocal pos
            if pos + 4 > len(raw):
                issues.append(f"{name}: unexpected end")
                return None
            value = int.from_bytes(raw[pos : pos + 4], "little", signed=False)
            pos += 4
            return value

        def read_i32(name: str) -> Optional[int]:
            nonlocal pos
            if pos + 4 > len(raw):
                issues.append(f"{name}: unexpected end")
                return None
            value = int.from_bytes(raw[pos : pos + 4], "little", signed=True)
            pos += 4
            return value

        unknown = read_u32("Unknown")
        if unknown is None:
            self._attach_validation(node, issues)
            return node
        node.children.append(DetailNode("Unknown", f"0x{unknown:08X} ({unknown})"))

        location_marker = read_u32("Location Marker")
        if location_marker is None:
            self._attach_validation(node, issues)
            return node
        node.children.append(DetailNode("Location Marker", f"0x{location_marker:08X} ({location_marker})"))

        worldspace_id = read_u32("Worldspace")
        if worldspace_id is None:
            self._attach_validation(node, issues)
            return node
        world_text, world_refs = self._format_formid_value(worldspace_id, "WRLD")
        node.children.append(DetailNode("Worldspace", world_text, world_refs))

        if worldspace_id == 0:
            cell_id = read_u32("Cell")
            if cell_id is not None:
                cell_text, cell_refs = self._format_formid_value(cell_id, "CELL")
                node.children.append(DetailNode("Cell", cell_text, cell_refs))
        else:
            if pos + 4 <= len(raw):
                grid_y = int.from_bytes(raw[pos : pos + 2], "little", signed=True)
                grid_x = int.from_bytes(raw[pos + 2 : pos + 4], "little", signed=True)
                pos += 4
                node.children.append(DetailNode("Grid (Y/X)", f"{grid_y}/{grid_x}"))
            else:
                issues.append("Grid data truncated")

        num_vertices = read_i32("Vertex Count")
        if num_vertices is None:
            self._attach_validation(node, issues)
            return node
        node.children.append(DetailNode("Vertex Count", str(num_vertices)))
        if num_vertices > 0:
            need = num_vertices * 12
            if pos + need > len(raw):
                issues.append("Vertex data truncated")
                self._attach_validation(node, issues)
                return node
            pos += need

        num_tris = read_i32("Triangle Count")
        if num_tris is None:
            self._attach_validation(node, issues)
            return node
        node.children.append(DetailNode("Triangle Count", str(num_tris)))
        if num_tris > 0:
            need = num_tris * 16
            if pos + need > len(raw):
                issues.append("Triangle data truncated")
                self._attach_validation(node, issues)
                return node
            pos += need

        if pos < len(raw):
            node.children.append(DetailNode("Remaining", f"{len(raw) - pos} bytes"))
        self._attach_validation(node, issues)
        return node

    def _format_text_candidate(self, field_obj: Field) -> Optional[str]:
        text = self._format_localized_or_text(field_obj)
        if text is None:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        if "\\" in stripped or "/" in stripped:
            return text
        alpha = sum(ch.isalpha() for ch in stripped)
        digit = sum(ch.isdigit() for ch in stripped)
        if alpha >= 2:
            return text
        if alpha >= 1 and len(stripped) >= 4:
            return text
        if digit >= 2 and len(stripped) >= 4 and " " in stripped:
            return text
        return None

    def _format_hedr_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        if field_obj.size < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        version, num_records, next_id = struct.unpack_from("<fII", field_obj.raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Version", f"{version:.2f}"))
        node.children.append(DetailNode("Records", f"{num_records}"))
        node.children.append(DetailNode("Next ID", f"0x{next_id:08X}"))
        return node

    def _format_kwda(self, field_obj: Field) -> str:
        text, _ = self._kwda_refs_and_text(field_obj)
        return text

    def _format_mast(self, field_obj: Field) -> str:
        text = decode_text(field_obj.raw)
        if text:
            return text
        return self._format_numeric(field_obj)

    def _kwda_refs_and_text(self, field_obj: Field) -> Tuple[str, List[Tuple[str, int]]]:
        if not self.plugin or not self.plugin.formid_resolver:
            return self._format_numeric(field_obj), []
        raw = field_obj.raw
        if len(raw) % 4 != 0:
            return self._format_numeric(field_obj), []
        count = len(raw) // 4
        parts: List[str] = []
        refs: List[Tuple[str, int]] = []
        max_preview = min(count, 8)
        for i in range(max_preview):
            form_id = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little")
            refs.append(("KYWD", form_id))
            parts.append(self.plugin.formid_resolver.describe(form_id, "KYWD"))
        suffix = ", ".join(parts)
        if count > max_preview:
            suffix += f" (+{count - max_preview} more)"
        prefix = f"[{count}] " if count else "[0]"
        text = prefix + suffix if suffix else prefix
        return text, refs

    def _format_obnd_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        x1, y1, z1, x2, y2, z2 = struct.unpack_from("<hhhhhh", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("X1", str(x1)))
        node.children.append(DetailNode("Y1", str(y1)))
        node.children.append(DetailNode("Z1", str(z1)))
        node.children.append(DetailNode("X2", str(x2)))
        node.children.append(DetailNode("Y2", str(y2)))
        node.children.append(DetailNode("Z2", str(z2)))
        return node

    _WEAP_ANIM_TYPE = {
        0: "HandToHandMelee",
        1: "OneHandSword",
        2: "OneHandDagger",
        3: "OneHandAxe",
        4: "OneHandMace",
        5: "TwoHandSword",
        6: "TwoHandAxe",
        7: "Bow",
        8: "Staff",
        9: "Crossbow",
    }

    _WEAP_ON_HIT = {
        0: "No formula behaviour",
        1: "Dismember only",
        2: "Explode only",
        3: "No dismember/explode",
    }

    _WEAP_FLAGS_1 = (
        (0x0001, "Ignores Normal Weapon Resistance"),
        (0x0002, "Automatic (unused)"),
        (0x0004, "Has Scope (unused)"),
        (0x0008, "Can't Drop"),
        (0x0010, "Hide Backpack (unused)"),
        (0x0020, "Embedded Weapon (unused)"),
        (0x0040, "Don't Use 1st Person IS Anim (unused)"),
        (0x0080, "Non-playable"),
    )

    _WEAP_FLAGS_2 = (
        (0x00000001, "Player Only"),
        (0x00000002, "NPCs Use Ammo"),
        (0x00000004, "No Jam After Reload (unused)"),
        (0x00000008, "Unknown 4"),
        (0x00000010, "Minor Crime"),
        (0x00000020, "Range Fixed"),
        (0x00000040, "Not Used in Normal Combat"),
        (0x00000080, "Unknown 8"),
        (0x00000100, "Don't Use 3rd Person IS Anim (unused)"),
        (0x00000200, "Burst Shot"),
        (0x00000400, "Rumble - Alternate"),
        (0x00000800, "Long Bursts"),
        (0x00001000, "Non-hostile"),
        (0x00002000, "Bound Weapon"),
    )

    _WEAP_SKILL = {
        0: "Unknown 1",
        1: "Unknown 2",
        2: "Unknown 3",
        3: "Unknown 4",
        4: "Unknown 5",
        5: "Unknown 6",
        6: "One Handed",
        7: "Two Handed",
        8: "Archery",
        9: "Block",
        10: "Smithing",
        11: "Heavy Armor",
        12: "Light Armor",
        13: "Pickpocket",
        14: "Lockpicking",
        15: "Sneak",
        16: "Alchemy",
        17: "Speech",
        18: "Alteration",
        19: "Conjuration",
        20: "Destruction",
        21: "Illusion",
        22: "Restoration",
        23: "Enchanting",
    }

    def _format_weap_data_node(self, field_obj: Field) -> DetailNode:
        """WEAP DATA - Game Data: Value, Weight, Damage."""
        label = "DATA - Game Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 10:
            issues.append(f"Unexpected WEAP DATA size {len(raw)} (expected 10)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        value, weight, damage = struct.unpack_from("<IfH", raw, 0)
        node.children.append(DetailNode("Value", str(value)))
        node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        node.children.append(DetailNode("Damage", str(damage)))
        self._attach_validation(node, issues)
        return node

    def _format_weap_dnam_node(self, field_obj: Field) -> DetailNode:
        """WEAP DNAM - Data (Animation Type, Speed, Reach, Flags, etc.)."""
        label = "DNAM - Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 100:
            issues.append(f"Unexpected WEAP DNAM size {len(raw)} (expected 100)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        anim_type = raw[0]
        speed, reach = struct.unpack_from("<ff", raw, 4)
        flags1 = int.from_bytes(raw[12:14], "little", signed=False)
        sight_fov = struct.unpack_from("<f", raw, 16)[0]
        vats_chance = raw[24]
        attack_anim = raw[25]
        n_projectiles = raw[26]
        range_min, range_max = struct.unpack_from("<ff", raw, 28)
        on_hit = int.from_bytes(raw[36:40], "little", signed=False)
        flags2 = int.from_bytes(raw[40:44], "little", signed=False)
        anim_mult, fire_rate = struct.unpack_from("<ff", raw, 44)
        rumble_left, rumble_right, rumble_dur = struct.unpack_from("<fff", raw, 52)
        override_dmg, attack_shots = struct.unpack_from("<ff", raw, 64)
        skill = struct.unpack_from("<i", raw, 76)[0]
        resist = struct.unpack_from("<i", raw, 88)[0]
        stagger = struct.unpack_from("<f", raw, 96)[0]
        anim_name = self._WEAP_ANIM_TYPE.get(anim_type, str(anim_type))
        node.children.append(DetailNode("Animation Type", f"{anim_type} ({anim_name})"))
        node.children.append(DetailNode("Speed", f"{speed:.6g}"))
        node.children.append(DetailNode("Reach", f"{reach:.6g}"))
        flags1_names = [n for mask, n in self._WEAP_FLAGS_1 if flags1 & mask]
        flags1_str = "0x{:04X}".format(flags1)
        if flags1_names:
            flags1_str += " (" + ", ".join(flags1_names) + ")"
        node.children.append(DetailNode("Flags", flags1_str))
        node.children.append(DetailNode("Sight FOV", f"{sight_fov:.6g}"))
        node.children.append(DetailNode("Base VATS To-Hit Chance", str(vats_chance)))
        node.children.append(DetailNode("Attack Animation", str(attack_anim)))
        node.children.append(DetailNode("# Projectiles", str(n_projectiles)))
        node.children.append(DetailNode("Range Min", f"{range_min:.6g}"))
        node.children.append(DetailNode("Range Max", f"{range_max:.6g}"))
        on_hit_name = self._WEAP_ON_HIT.get(on_hit, str(on_hit))
        node.children.append(DetailNode("On Hit", f"{on_hit} ({on_hit_name})"))
        flags2_names = [n for mask, n in self._WEAP_FLAGS_2 if flags2 & mask]
        flags2_str = "0x{:08X}".format(flags2)
        if flags2_names:
            flags2_str += " (" + ", ".join(flags2_names) + ")"
        node.children.append(DetailNode("Flags2", flags2_str))
        node.children.append(DetailNode("Animation Attack Mult", f"{anim_mult:.6g}"))
        node.children.append(DetailNode("Fire Rate", f"{fire_rate:.6g}"))
        node.children.append(DetailNode("Rumble - Left Motor Strength", f"{rumble_left:.6g}"))
        node.children.append(DetailNode("Rumble - Right Motor Strength", f"{rumble_right:.6g}"))
        node.children.append(DetailNode("Rumble - Duration", f"{rumble_dur:.6g}"))
        node.children.append(DetailNode("Override - Damage to Weapon Mult", f"{override_dmg:.6g}"))
        node.children.append(DetailNode("Attack Shots/Sec", f"{attack_shots:.6g}"))
        skill_name = self._WEAP_SKILL.get(skill, str(skill))
        node.children.append(DetailNode("Skill", f"{skill} ({skill_name})"))
        node.children.append(DetailNode("Resist", str(resist)))
        node.children.append(DetailNode("Stagger", f"{stagger:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_weap_crdt_node(self, field_obj: Field) -> DetailNode:
        """WEAP CRDT - Critical Data."""
        label = "CRDT - Critical Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 12:
            issues.append(f"Unexpected WEAP CRDT size {len(raw)} (expected 12+)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        damage = int.from_bytes(raw[0:2], "little", signed=False)
        pct_mult = struct.unpack_from("<f", raw, 4)[0]
        on_death = raw[8]
        effect_offset = 16 if len(raw) >= 20 else 12
        if len(raw) >= effect_offset + 4:
            effect_id = int.from_bytes(raw[effect_offset : effect_offset + 4], "little", signed=False)
            text, refs = self._format_formid_value(effect_id, "SPEL")
            node.children.append(DetailNode("Damage", str(damage)))
            node.children.append(DetailNode("% Mult", f"{pct_mult:.6g}"))
            node.children.append(DetailNode("On Death", "Yes" if on_death else "No"))
            node.children.append(DetailNode("Effect", text, refs))
        else:
            node.children.append(DetailNode("Damage", str(damage)))
            node.children.append(DetailNode("% Mult", f"{pct_mult:.6g}"))
            node.children.append(DetailNode("On Death", "Yes" if on_death else "No"))
        self._attach_validation(node, issues)
        return node

    def _format_armo_data_node(self, field_obj: Field) -> DetailNode:
        """ARMO DATA - Value, Weight."""
        label = "DATA - Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 8:
            issues.append(f"Unexpected ARMO DATA size {len(raw)} (expected 8)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        value, weight = struct.unpack_from("<if", raw, 0)
        node.value = f"Value: {value}, Weight: {weight:.6g}"
        node.children.append(DetailNode("Value", str(value)))
        node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_armo_dnam_node(self, field_obj: Field) -> DetailNode:
        """ARMO DNAM - Armor Rating (stored * 100 in file)."""
        label = "DNAM - Armor Rating"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 4:
            issues.append(f"Unexpected ARMO DNAM size {len(raw)} (expected 4)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        raw_value = struct.unpack_from("<i", raw, 0)[0]
        displayed = raw_value / 100.0 if raw_value != 0 else 0
        node.value = f"{displayed:.2f}"
        node.children.append(DetailNode("Armor Rating", f"{displayed:.2f}"))
        self._attach_validation(node, issues)
        return node

    def _format_biped_object_node(self, field_obj: Field) -> DetailNode:
        """BOD2/BODT - Biped Body Template (slots and armor type)."""
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []

        if len(raw) < 8:
            issues.append(f"Unexpected {field_obj.signature} size {len(raw)} (expected at least 8)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node

        # First 4 bytes are always Biped Object flags (slots)
        slots_mask = int.from_bytes(raw[0:4], "little", signed=False)
        
        # Decompose slots
        slot_nodes = []
        for bit in range(32):
            if slots_mask & (1 << bit):
                name = self._biped_slot_names.get(bit, f"{30 + bit}: Unknown")
                slot_nodes.append(DetailNode(f"Slot {30 + bit}", name))
        
        slots_summary = f"{len(slot_nodes)} slots" if slot_nodes else "—"
        slots_parent = DetailNode("Biped Body Slots", slots_summary)
        slots_parent.children = slot_nodes
        node.children.append(slots_parent)

        # Remaining data
        if field_obj.signature == "BODT" and len(raw) >= 12:
            # BODT has 4 bytes flags/junk between slots and armor type
            flags = raw[4]
            junk = raw[5:8]
            if any(b != 0 for b in junk):
                issues.append(f"Non-zero junk bytes in BODT: {junk.hex(' ').upper()}")
            node.children.append(DetailNode("Flags", f"0x{flags:02X}"))
            armor_type_raw = int.from_bytes(raw[8:12], "little", signed=False)
        else:
            # BOD2 has armor type immediately after slots
            armor_type_raw = int.from_bytes(raw[4:8], "little", signed=False)

        try:
            armor_type_name = ArmorType(armor_type_raw).name.replace("_", " ").title()
        except ValueError:
            armor_type_name = f"Unknown ({armor_type_raw})"
        
        node.children.append(DetailNode("Armor Type", armor_type_name))

        if not slot_nodes:
             node.value = "—"

        self._attach_validation(node, issues)
        return node

    def _format_book_data_node(self, field_obj: Field) -> DetailNode:
        """BOOK DATA - Flags, Type, Teaches, Value, Weight."""
        label = "DATA - Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 16:
            issues.append(f"Unexpected BOOK DATA size {len(raw)} (expected 16)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        flags = raw[0]
        book_type = raw[1]
        teaches = int.from_bytes(raw[4:8], "little", signed=False)
        value = int.from_bytes(raw[8:12], "little", signed=False)
        weight = struct.unpack_from("<f", raw, 12)[0]
        flag_names = []
        if flags & 0x01:
            flag_names.append("Teaches Skill")
        if flags & 0x02:
            flag_names.append("Can't be Taken")
        if flags & 0x04:
            flag_names.append("Teaches Spell")
        type_name = "Book/Tome" if book_type == 0 else ("Note/Scroll" if book_type == 255 else str(book_type))
        flags_str = "0x{:02X}".format(flags)
        if flag_names:
            flags_str += " (" + ", ".join(flag_names) + ")"
        node.children.append(DetailNode("Flags", flags_str))
        node.children.append(DetailNode("Type", f"{book_type} ({type_name})"))
        if flags & 0x01:
            skill_name = self._WEAP_SKILL.get(teaches, str(teaches))
            node.children.append(DetailNode("Teaches", f"{teaches} ({skill_name})"))
        elif flags & 0x04:
            text, refs = self._format_formid_value(teaches, "SPEL")
            node.children.append(DetailNode("Teaches", text, refs))
        else:
            node.children.append(DetailNode("Teaches", str(teaches)))
        node.children.append(DetailNode("Value", str(value)))
        node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_alch_data_node(self, field_obj: Field) -> DetailNode:
        """ALCH DATA - Weight (single float)."""
        label = "DATA - Weight"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 4:
            issues.append(f"Unexpected ALCH DATA size {len(raw)} (expected 4)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        weight = struct.unpack_from("<f", raw, 0)[0]
        node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_ammo_data_node(self, field_obj: Field) -> DetailNode:
        """AMMO DATA - Projectile, Flags, Damage, Value, (Weight)."""
        label = "DATA - Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 16:
            issues.append(f"Unexpected AMMO DATA size {len(raw)} (expected 16+)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        proj_id = int.from_bytes(raw[0:4], "little", signed=False)
        flags = int.from_bytes(raw[4:8], "little", signed=False)
        damage = struct.unpack_from("<f", raw, 8)[0]
        value = int.from_bytes(raw[12:16], "little", signed=False)
        flag_names = []
        if flags & 1:
            flag_names.append("Ignores Normal Weapon Resistance")
        if flags & 2:
            flag_names.append("Non-Playable")
        if flags & 4:
            flag_names.append("Non-Bolt")
        text, refs = self._format_formid_value(proj_id, "PROJ")
        node.children.append(DetailNode("Projectile", text, refs))
        flags_str = "0x{:08X}".format(flags)
        if flag_names:
            flags_str += " (" + ", ".join(flag_names) + ")"
        node.children.append(DetailNode("Flags", flags_str))
        node.children.append(DetailNode("Damage", f"{damage:.6g}"))
        node.children.append(DetailNode("Value", str(value)))
        if len(raw) >= 20:
            weight = struct.unpack_from("<f", raw, 16)[0]
            node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_misc_data_node(self, field_obj: Field) -> DetailNode:
        """MISC DATA - Value, Weight (same structure as ARMO DATA)."""
        label = "DATA - Data"
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 8:
            issues.append(f"Unexpected MISC DATA size {len(raw)} (expected 8)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        value, weight = struct.unpack_from("<if", raw, 0)
        node.children.append(DetailNode("Value", str(value)))
        node.children.append(DetailNode("Weight", f"{weight:.6g}"))
        self._attach_validation(node, issues)
        return node

    def _format_rgba_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 4:
            return DetailNode(label, self._format_numeric(field_obj))
        r, g, b, a = struct.unpack_from("<BBBB", raw, 0)
        node = DetailNode(label, f"{r}/{g}/{b}/{a}")
        node.children.append(DetailNode("R", str(r)))
        node.children.append(DetailNode("G", str(g)))
        node.children.append(DetailNode("B", str(b)))
        node.children.append(DetailNode("A", str(a)))
        return node

    def _format_binary_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, f"binary blob ({len(raw)} bytes)")
        if raw:
            node.children.append(DetailNode("CRC32", f"0x{zlib.crc32(raw) & 0xFFFFFFFF:08X}"))
        return node

    def _format_gmst_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        editor_id = self.record.editor_id
        if not editor_id:
            for field in self.record.fields:
                if field.signature == "EDID":
                    text = decode_text(field.raw)
                    if text:
                        editor_id = text
                    break
        type_char = editor_id[0].lower() if editor_id else None
        raw = field_obj.raw

        if type_char == "s":
            if self.plugin and self.plugin.localized and field_obj.size == 4:
                string_id = int.from_bytes(raw, "little", signed=False)
                resolved = self.plugin.strings.resolve(string_id)
                if resolved is not None:
                    return DetailNode(label, resolved)
                return DetailNode(label, f"StringID 0x{string_id:08X}")
            text = decode_text(raw)
            if text is not None:
                return DetailNode(label, text)
            return DetailNode(label, self._format_numeric(field_obj))

        if type_char == "i":
            if field_obj.size >= 4:
                value = struct.unpack_from("<i", raw, 0)[0]
                return DetailNode(label, f"{value} (0x{value & 0xFFFFFFFF:08X})")
            return DetailNode(label, self._format_numeric(field_obj))

        if type_char == "f":
            if field_obj.size >= 4:
                value = struct.unpack_from("<f", raw, 0)[0]
                return DetailNode(label, f"{value:.6g}")
            return DetailNode(label, self._format_numeric(field_obj))

        if type_char == "b":
            if field_obj.size >= 4:
                value = int.from_bytes(raw[:4], "little", signed=False)
                return DetailNode(label, "Yes" if value else "No")
            return DetailNode(label, self._format_numeric(field_obj))

        return DetailNode(label, self._format_numeric(field_obj))

    def _format_rnam_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 8:
            return DetailNode(label, self._format_numeric(field_obj))
        pos = 0
        cell_x, cell_y = struct.unpack_from("<hh", raw, pos)
        pos += 4
        count = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        node.children.append(DetailNode("Cell X", str(cell_x)))
        node.children.append(DetailNode("Cell Y", str(cell_y)))
        node.children.append(DetailNode("Count", str(count)))
        expected = 8 + count * 8
        if len(raw) < expected:
            issues.append(f"Unexpected RNAM size {len(raw)} (expected {expected})")
        preview = min(count, 16)
        for i in range(preview):
            if pos + 8 > len(raw):
                break
            form_id = struct.unpack_from("<I", raw, pos)[0]
            x = struct.unpack_from("<h", raw, pos + 4)[0]
            y = struct.unpack_from("<h", raw, pos + 6)[0]
            pos += 8
            text, refs = self._format_formid_value(form_id, "REFR")
            node.children.append(DetailNode(f"Entry {i}", f"{text} ({x},{y})", refs))
        if count > preview:
            node.children.append(DetailNode("More", f"+{count - preview} entries"))
        self._attach_validation(node, issues)
        return node

    def _format_wrld_mhdt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 8:
            return DetailNode(label, self._format_numeric(field_obj))
        min_x, max_x, min_y, max_y = struct.unpack_from("<hhhh", raw, 0)
        node.children.append(DetailNode("Min X", str(min_x)))
        node.children.append(DetailNode("Max X", str(max_x)))
        node.children.append(DetailNode("Min Y", str(min_y)))
        node.children.append(DetailNode("Max Y", str(max_y)))
        cell_count = max(0, (max_x - min_x + 1)) * max(0, (max_y - min_y + 1))
        node.children.append(DetailNode("Cells", str(cell_count)))
        data = raw[8:]
        available = len(data) // 4
        if cell_count and available < cell_count:
            issues.append(f"Unexpected MHDT size {len(raw)} (expected {8 + cell_count * 4})")
        if data:
            min_val = min(data)
            max_val = max(data)
            node.children.append(DetailNode("Value Min", str(min_val)))
            node.children.append(DetailNode("Value Max", str(max_val)))
        preview = min(available, 8)
        for i in range(preview):
            chunk = data[i * 4 : i * 4 + 4]
            if len(chunk) < 4:
                break
            values = "/".join(str(b) for b in chunk)
            node.children.append(DetailNode(f"Cell {i}", values))
        if available > preview:
            node.children.append(DetailNode("More", f"+{available - preview} entries"))
        self._attach_validation(node, issues)
        return node

    def _format_cell_mhdt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 4:
            return DetailNode(label, self._format_numeric(field_obj))
        header = struct.unpack_from("<I", raw, 0)[0]
        data = raw[4:]
        if len(raw) != 1028:
            issues.append(f"Unexpected MHDT size {len(raw)} (expected 1028)")
        node.children.append(DetailNode("Unknown", f"0x{header:08X} ({header})"))
        if data:
            node.children.append(DetailNode("Value Min", str(min(data))))
            node.children.append(DetailNode("Value Max", str(max(data))))
            node.children.append(DetailNode("Values", str(len(data))))
        self._attach_validation(node, issues)
        return node

    def _format_xlig_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 16:
            return DetailNode(label, self._format_numeric(field_obj))
        fov, fade, end_dist, shadow_bias = struct.unpack_from("<4f", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("FOV Offset", f"{fov:.6g}"))
        node.children.append(DetailNode("Fade Offset", f"{fade:.6g}"))
        node.children.append(DetailNode("End Distance", f"{end_dist:.6g}"))
        node.children.append(DetailNode("Shadow Bias", f"{shadow_bias:.6g}"))
        if len(raw) >= 20:
            extra = struct.unpack_from("<I", raw, 16)[0]
            node.children.append(DetailNode("Unknown", f"0x{extra:08X} ({extra})"))
        return node

    def _format_xrgd_node(self, field_obj: Field) -> DetailNode:
        return self._format_binary_node(field_obj)

    def _format_pkdt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        misc_flags, = struct.unpack_from("<I", raw, 0)
        package_type = raw[4]
        interrupt_override = raw[5]
        preferred_speed = raw[6]
        unknown = raw[7]
        interrupt_flags, = struct.unpack_from("<I", raw, 8)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Misc Flags", f"0x{misc_flags:08X} ({misc_flags})"))
        node.children.append(DetailNode("Package Type", str(package_type)))
        node.children.append(DetailNode("Interrupt Override", str(interrupt_override)))
        node.children.append(DetailNode("Preferred Speed", str(preferred_speed)))
        node.children.append(DetailNode("Unknown", str(unknown)))
        node.children.append(DetailNode("Interrupt Flags", f"0x{interrupt_flags:08X} ({interrupt_flags})"))
        return node

    def _format_psdt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        month = struct.unpack_from("<b", raw, 0)[0]
        weekday = struct.unpack_from("<b", raw, 1)[0]
        date = raw[2]
        hour = struct.unpack_from("<b", raw, 3)[0]
        minute = struct.unpack_from("<b", raw, 4)[0]
        unknown = raw[5:8]
        duration = struct.unpack_from("<I", raw, 8)[0]
        node = DetailNode(label, "")
        node.children.append(DetailNode("Month", str(month)))
        node.children.append(DetailNode("Day", str(weekday)))
        node.children.append(DetailNode("Date", str(date)))
        node.children.append(DetailNode("Hour", str(hour)))
        node.children.append(DetailNode("Minute", str(minute)))
        node.children.append(DetailNode("Unknown", "/".join(str(b) for b in unknown)))
        node.children.append(DetailNode("Duration", str(duration)))
        return node

    def _format_pkcu_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        unk1, template_id, unk2 = struct.unpack_from("<III", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Unknown 1", f"0x{unk1:08X} ({unk1})"))
        text, refs = self._format_formid_value(template_id, "PACK")
        node.children.append(DetailNode("Template", text, refs))
        node.children.append(DetailNode("Unknown 2", f"0x{unk2:08X} ({unk2})"))
        return node

    def _format_aidt_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 20:
            issues.append(f"Unexpected AIDT size {len(raw)} (expected 20)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        aggression, confidence, energy, morality, mood, assistance = struct.unpack_from("<6B", raw, 0)
        radius, unused = struct.unpack_from("<2B", raw, 6)
        warn, warn_attack, attack = struct.unpack_from("<III", raw, 8)
        node.children.append(DetailNode("Aggression", str(aggression)))
        node.children.append(DetailNode("Confidence", str(confidence)))
        node.children.append(DetailNode("Energy", str(energy)))
        node.children.append(DetailNode("Morality", str(morality)))
        node.children.append(DetailNode("Mood", str(mood)))
        node.children.append(DetailNode("Assistance", str(assistance)))
        node.children.append(DetailNode("Aggro Radius", str(radius)))
        node.children.append(DetailNode("Aggro Unused", str(unused)))
        node.children.append(DetailNode("Warn", str(warn)))
        node.children.append(DetailNode("Warn/Attack", str(warn_attack)))
        node.children.append(DetailNode("Attack", str(attack)))
        self._attach_validation(node, issues)
        return node

    def _format_atkd_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 44:
            return DetailNode(label, self._format_numeric(field_obj))
        pos = 0
        damage_mult, = struct.unpack_from("<f", raw, pos)
        pos += 4
        attack_chance, = struct.unpack_from("<f", raw, pos)
        pos += 4
        attack_spell = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        flags = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        attack_angle, = struct.unpack_from("<f", raw, pos)
        pos += 4
        strike_angle, = struct.unpack_from("<f", raw, pos)
        pos += 4
        stagger, = struct.unpack_from("<f", raw, pos)
        pos += 4
        attack_type = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        knockdown, = struct.unpack_from("<f", raw, pos)
        pos += 4
        recovery, = struct.unpack_from("<f", raw, pos)
        pos += 4
        stamina_mult, = struct.unpack_from("<f", raw, pos)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Damage Mult", f"{damage_mult:.6g}"))
        node.children.append(DetailNode("Attack Chance", f"{attack_chance:.6g}"))
        spell_text, spell_refs = self._format_formid_value(attack_spell, "SPEL")
        node.children.append(DetailNode("Attack Spell", spell_text, spell_refs))
        node.children.append(DetailNode("Attack Flags", f"0x{flags:08X} ({flags})"))
        node.children.append(DetailNode("Attack Angle", f"{attack_angle:.6g}"))
        node.children.append(DetailNode("Strike Angle", f"{strike_angle:.6g}"))
        node.children.append(DetailNode("Stagger", f"{stagger:.6g}"))
        type_text, type_refs = self._format_formid_value(attack_type, "KYWD")
        node.children.append(DetailNode("Attack Type", type_text, type_refs))
        node.children.append(DetailNode("Knockdown", f"{knockdown:.6g}"))
        node.children.append(DetailNode("Recovery Time", f"{recovery:.6g}"))
        node.children.append(DetailNode("Stamina Mult", f"{stamina_mult:.6g}"))
        return node

    def _format_idle_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 6:
            return DetailNode(label, self._format_numeric(field_obj))
        min_loop, max_loop, flags, unknown, delay = struct.unpack_from("<BBBBH", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Min Loop", str(min_loop)))
        node.children.append(DetailNode("Max Loop", str(max_loop)))
        node.children.append(DetailNode("Flags", f"0x{flags:02X} ({flags})"))
        node.children.append(DetailNode("Unknown", str(unknown)))
        node.children.append(DetailNode("Replay Delay", str(delay)))
        return node

    def _format_sndr_bnam_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 6:
            return DetailNode(label, self._format_numeric(field_obj))
        freq_shift, variance, priority, db_var, attenuation = struct.unpack_from("<bBBBH", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Frequency Shift", str(freq_shift)))
        node.children.append(DetailNode("Frequency Variance", str(variance)))
        node.children.append(DetailNode("Priority", str(priority)))
        node.children.append(DetailNode("dB Variance", str(db_var)))
        node.children.append(DetailNode("Attenuation", str(attenuation)))
        return node

    def _format_efit_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 12:
            return DetailNode(label, self._format_numeric(field_obj))
        magnitude, area, duration = struct.unpack_from("<fII", raw, 0)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Magnitude", f"{magnitude:.6g}"))
        node.children.append(DetailNode("Area", str(area)))
        node.children.append(DetailNode("Duration", str(duration)))
        return node

    def _format_spit_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 36:
            return DetailNode(label, self._format_numeric(field_obj))
        offset = 0
        base_cost, = struct.unpack_from("<I", raw, offset)
        offset += 4
        flags, = struct.unpack_from("<I", raw, offset)
        offset += 4
        spell_type, = struct.unpack_from("<I", raw, offset)
        offset += 4
        charge_time, = struct.unpack_from("<f", raw, offset)
        offset += 4
        cast_type, = struct.unpack_from("<I", raw, offset)
        offset += 4
        delivery, = struct.unpack_from("<I", raw, offset)
        offset += 4
        cast_duration, = struct.unpack_from("<f", raw, offset)
        offset += 4
        cast_range, = struct.unpack_from("<f", raw, offset)
        offset += 4
        half_cost_perk, = struct.unpack_from("<I", raw, offset)
        node = DetailNode(label, "")
        node.children.append(DetailNode("Base Cost", str(base_cost)))
        node.children.append(DetailNode("Flags", f"0x{flags:08X}"))
        node.children.append(DetailNode("Type", str(spell_type)))
        node.children.append(DetailNode("Charge Time", f"{charge_time:.6g}"))
        node.children.append(DetailNode("Cast Type", str(cast_type)))
        node.children.append(DetailNode("Delivery", str(delivery)))
        node.children.append(DetailNode("Cast Duration", f"{cast_duration:.6g}"))
        node.children.append(DetailNode("Range", f"{cast_range:.6g}"))
        text, refs = self._format_formid_value(half_cost_perk, "PERK")
        node.children.append(DetailNode("Half-cost Perk", text, refs))
        return node

    def _format_mgef_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        expected = 112
        if len(raw) != expected:
            issues.append(f"Unexpected DATA size {len(raw)} (expected {expected})")
        layout = [
            ("Flags", "u32"),
            ("Base Cost", "f32"),
            ("Assoc. Item", "formid"),
            ("Magic Skill", "s32"),
            ("Resist Value", "s32"),
            ("Counter Effect Count", "u16count"),
            ("Casting Light", "formid"),
            ("Taper Weight", "f32"),
            ("Hit Shader", "formid"),
            ("Enchant Shader", "formid"),
            ("Minimum Skill Level", "u32"),
            ("Spellmaking Area", "u32"),
            ("Spellmaking Casting Time", "f32"),
            ("Taper Curve", "f32"),
            ("Taper Duration", "f32"),
            ("Second AV Weight", "f32"),
            ("Effect Type", "u32"),
            ("Actor Value", "s32"),
            ("Projectile", "formid"),
            ("Explosion", "formid"),
            ("Casting Type", "u32"),
            ("Delivery", "u32"),
            ("Second Actor Value", "s32"),
            ("Casting Art", "formid"),
            ("Hit Effect Art", "formid"),
            ("Impact Data", "formid"),
            ("Skill Usage Multiplier", "f32"),
            ("Dual Casting Art", "formid"),
            ("Dual Casting Scale", "f32"),
        ]
        pos = 0
        for name, kind in layout:
            if pos + 4 > len(raw):
                break
            chunk = raw[pos : pos + 4]
            pos += 4
            if kind == "u32":
                value = int.from_bytes(chunk, "little", signed=False)
                node.children.append(DetailNode(name, str(value)))
            elif kind == "s32":
                value = int.from_bytes(chunk, "little", signed=True)
                node.children.append(DetailNode(name, str(value)))
            elif kind == "f32":
                value = struct.unpack("<f", chunk)[0]
                node.children.append(DetailNode(name, f"{value:.6g}"))
            elif kind == "u16count":
                value = int.from_bytes(chunk, "little", signed=False) & 0xFFFF
                node.children.append(DetailNode(name, str(value)))
            elif kind == "formid":
                form_id = int.from_bytes(chunk, "little", signed=False)
                text, refs = self._format_formid_value(form_id)
                node.children.append(DetailNode(name, text, refs))
                self._validate_formid(form_id, None, issues, name)
        if not node.children:
            node.value = self._format_numeric(field_obj)
        self._attach_validation(node, issues)
        return node

    def _format_sndd_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) % 4 != 0 or not raw:
            return DetailNode(label, self._format_numeric(field_obj))
        count = len(raw) // 4
        parts: List[str] = []
        refs: List[Tuple[Optional[str], int]] = []
        preview = min(count, 6)
        for i in range(preview):
            value = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little", signed=False)
            text, ref = self._format_formid_value(value)
            refs.extend(ref)
            parts.append(text)
        suffix = ", ".join(parts)
        if count > preview:
            suffix += f" (+{count - preview} more)"
        prefix = f"[{count}] " if count else "[0]"
        return DetailNode(label, prefix + suffix if suffix else prefix, refs)

    def _format_ctda_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        if len(raw) < 32:
            return DetailNode(label, self._format_numeric(field_obj))
        type_val = raw[0]
        flag_bits = type_val & 0x1F
        use_global = bool(flag_bits & 0x04)
        comp_raw = raw[4:8]
        function = int.from_bytes(raw[8:10], "little", signed=False)
        param1 = int.from_bytes(raw[12:16], "little", signed=False)
        param2 = int.from_bytes(raw[16:20], "little", signed=False)
        run_on = int.from_bytes(raw[20:24], "little", signed=False)
        reference = int.from_bytes(raw[24:28], "little", signed=False)
        param3 = int.from_bytes(raw[28:32], "little", signed=True)

        run_on_name = self._run_on_names.get(run_on)
        text1, refs1 = self._format_param_value(param1)
        text2, refs2 = self._format_param_value(param2)
        
        comp_text = ""
        if use_global:
            comp_formid = int.from_bytes(comp_raw, "little", signed=False)
            comp_text = f"0x{comp_formid:08X}"
        else:
            comp_value = struct.unpack("<f", comp_raw)[0]
            comp_text = f"{comp_value:.6g}"

        summary = self._format_ctda_summary(
            run_on_name,
            run_on,
            f"0x{reference:08X}" if reference else "0",
            function,
            text1,
            text2,
            comp_text,
            type_val,
        )

        node = DetailNode(f"{label}: {summary}", "")
        node.children.append(DetailNode("Type", self._format_ctda_type(type_val)))

        comp_formid = int.from_bytes(comp_raw, "little", signed=False)
        comp_value = struct.unpack("<f", comp_raw)[0]
        if use_global and comp_formid:
            comp_text_ui, comp_refs = self._format_formid_value(comp_formid, "GLOB")
            node.children.append(DetailNode("Comparison Value", comp_text_ui, comp_refs))
        else:
            comp_text_ui = f"{comp_value:.6g}"
            node.children.append(DetailNode("Comparison Value", comp_text_ui))

        function_text = f"{function} (0x{function:04X})"
        node.children.append(DetailNode("Function", function_text))

        node.children.append(DetailNode("Parameter #1", text1, refs1))
        node.children.append(DetailNode("Parameter #2", text2, refs2))

        run_on_text = f"{run_on} ({run_on_name})" if run_on_name else str(run_on)
        node.children.append(DetailNode("Run On", run_on_text))

        if reference:
            reference_text_ui, reference_refs = self._format_formid_value(reference)
            node.children.append(DetailNode("Reference", reference_text_ui, reference_refs))
        else:
            node.children.append(DetailNode("Reference", "0"))

        param3_label = "Run On Index" if run_on in {5, 6, 7} else "Parameter #3"
        param3_text = "-1 (none)" if run_on in {5, 6, 7} and param3 == -1 else str(param3)
        node.children.append(DetailNode(param3_label, param3_text))
        return node

    def _format_ctda_type(self, type_val: int) -> str:
        operator = self._ctda_operator_name(type_val)
        flags = type_val & 0x1F
        flag_names: List[str] = []
        if flags & 0x01:
            flag_names.append("OR")
        if flags & 0x02:
            flag_names.append("Use Aliases")
        if flags & 0x04:
            flag_names.append("Use Global")
        if flags & 0x08:
            flag_names.append("Use Pack Data")
        if flags & 0x10:
            flag_names.append("Swap Subject and Target")
        base = f"{type_val} (0x{type_val:02X}) {operator}"
        if flag_names:
            return f"{base}; {', '.join(flag_names)}"
        return base

    def _ctda_operator_name(self, type_val: int) -> str:
        operator_val = (type_val >> 5) & 0x07
        operator_names = {
            0: "Equal to",
            1: "Not equal to",
            2: "Greater than",
            3: "Greater than or equal to",
            4: "Less than",
            5: "Less than or equal to",
        }
        return operator_names.get(operator_val, f"Operator {operator_val}")

    def _ctda_operator_symbol(self, type_val: int) -> str:
        operator_val = (type_val >> 5) & 0x07
        operator_symbols = {
            0: "==",
            1: "!=",
            2: ">",
            3: ">=",
            4: "<",
            5: "<=",
        }
        return operator_symbols.get(operator_val, f"op{operator_val}")

    def _format_ctda_summary(
        self,
        run_on_name: Optional[str],
        run_on: int,
        reference_text: str,
        function: int,
        param1_text: str,
        param2_text: str,
        comp_text: str,
        type_val: int,
    ) -> str:
        op = self._ctda_operator_symbol(type_val)
        func_text = f"Func 0x{function:04X}"
        base_ref = run_on_name or f"Run On {run_on}"
        if reference_text != "0":
            base_ref = f"{base_ref}: {reference_text}"
        return f"{base_ref}.{func_text}({param1_text}, {param2_text}) {op} {comp_text}"

    def _format_param_value(self, value: int) -> Tuple[str, List[Tuple[Optional[str], int]]]:
        if value == 0:
            return "0", []
        if self.plugin and self.plugin.formid_resolver:
            target = self.plugin.formid_resolver.get(value)
            if target is not None:
                return self._format_formid_value(value, target.signature)
        return f"{value} (0x{value:08X})", []

    def _validate_formid(
        self,
        form_id: int,
        signature: Optional[str],
        issues: List[str],
        label: str,
    ) -> None:
        if form_id == 0 or not self.plugin or not self.plugin.formid_resolver:
            return
        if self.plugin.formid_resolver.get(form_id) is not None:
            return
        master = self.plugin.formid_resolver.master_name((form_id >> 24) & 0xFF)
        if master is None:
            hi = (form_id >> 24) & 0xFF
            # If the FormID is from a plugin that isn't in our masters list,
            # and it's not a local FormID (00) or FE, it's probably an injected FormID
            # or we are missing load order context. In these cases, we don't want to
            # spam the log with "unresolved" warnings since we only have partial view.
            if hi != 0 and hi != 0xFE:
                return
            issues.append(f"{label}: unresolved FormID 0x{form_id:08X}")
            self._logger.warning(f"Unresolved FormID {form_id:08X} for {label}")

    def _attach_validation(self, node: DetailNode, issues: List[str]) -> None:
        if not issues:
            return
        node.name = f"{node.name} (validation: {issues[0]})"
        if len(issues) > 1:
            parent = DetailNode("Validation", f"{len(issues)} issue(s)")
            for issue in issues[1:]:
                parent.children.append(DetailNode("Issue", issue))
            node.children.append(parent)

    def _format_perk_main_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 5:
            issues.append(f"Unexpected DATA size {len(raw)} (expected 5)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        trait = raw[0]
        level = raw[1]
        ranks = raw[2]
        playable = raw[3]
        hidden = raw[4]
        if trait > 1:
            issues.append(f"Trait out of range: {trait}")
        if playable > 1:
            issues.append(f"Playable out of range: {playable}")
        if hidden > 1:
            issues.append(f"Hidden out of range: {hidden}")
        node.children.append(DetailNode("Trait", "Yes" if trait else "No"))
        node.children.append(DetailNode("Level", str(level)))
        node.children.append(DetailNode("Num Ranks", str(ranks)))
        node.children.append(DetailNode("Playable", "Yes" if playable else "No"))
        node.children.append(DetailNode("Hidden", "Yes" if hidden else "No"))
        self._attach_validation(node, issues)
        return node

    def _format_prke_header_node(self, field_obj: Field) -> Tuple[DetailNode, Optional[int]]:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 3:
            issues.append(f"Unexpected PRKE size {len(raw)} (expected 3)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node, None
        perk_type = raw[0]
        rank = raw[1]
        priority = raw[2]
        type_name = self._perk_effect_types.get(perk_type)
        type_text = f"{perk_type} ({type_name})" if type_name else str(perk_type)
        node.children.append(DetailNode("Type", type_text))
        node.children.append(DetailNode("Rank", str(rank)))
        node.children.append(DetailNode("Priority", str(priority)))
        self._attach_validation(node, issues)
        return node, perk_type

    def _format_perk_effect_data_node(
        self,
        field_obj: Field,
        perk_type: Optional[int],
    ) -> Tuple[DetailNode, Optional[int]]:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        entry_function: Optional[int] = None
        if perk_type is None:
            issues.append("Effect DATA without PRKE header")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node, entry_function
        if perk_type == 0:
            if len(raw) < 8:
                issues.append(f"Quest DATA size {len(raw)} (expected 8)")
                node.value = self._format_numeric(field_obj)
                self._attach_validation(node, issues)
                return node, entry_function
            quest_id = int.from_bytes(raw[0:4], "little", signed=False)
            stage = raw[4]
            text, refs = self._format_formid_value(quest_id, "QUST")
            node.children.append(DetailNode("Quest", text, refs))
            node.children.append(DetailNode("Quest Stage", str(stage)))
            self._validate_formid(quest_id, "QUST", issues, "Quest")
        elif perk_type == 1:
            if len(raw) < 4:
                issues.append(f"Ability DATA size {len(raw)} (expected 4)")
                node.value = self._format_numeric(field_obj)
                self._attach_validation(node, issues)
                return node, entry_function
            spell_id = int.from_bytes(raw[0:4], "little", signed=False)
            text, refs = self._format_formid_value(spell_id, "SPEL")
            node.children.append(DetailNode("Ability", text, refs))
            self._validate_formid(spell_id, "SPEL", issues, "Ability")
        elif perk_type == 2:
            if len(raw) < 3:
                issues.append(f"Entry Point DATA size {len(raw)} (expected 3)")
                node.value = self._format_numeric(field_obj)
                self._attach_validation(node, issues)
                return node, entry_function
            entry_point = raw[0]
            entry_function = raw[1]
            tab_count = raw[2]
            func_name = self._perk_function_types.get(entry_function)
            func_text = f"{entry_function} ({func_name})" if func_name else str(entry_function)
            node.children.append(DetailNode("Entry Point", str(entry_point)))
            node.children.append(DetailNode("Function", func_text))
            node.children.append(DetailNode("Condition Tab Count", str(tab_count)))
        else:
            issues.append(f"Unknown perk effect type {perk_type}")
            node.value = self._format_numeric(field_obj)
        self._attach_validation(node, issues)
        return node, entry_function

    def _format_epft_node(self, field_obj: Field) -> Tuple[DetailNode, Optional[int]]:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 1:
            issues.append(f"EPFT size {len(raw)} (expected 1)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node, None
        value = raw[0]
        name = self._perk_epft_types.get(value)
        text = f"{value} ({name})" if name else str(value)
        node.value = text
        if name is None:
            issues.append(f"Unknown EPFT value {value}")
        self._attach_validation(node, issues)
        return node, value

    def _format_epf3_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) < 4:
            issues.append(f"EPF3 size {len(raw)} (expected 4)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        flags = int.from_bytes(raw[0:2], "little", signed=False)
        fragment = int.from_bytes(raw[2:4], "little", signed=False)
        names: List[str] = []
        if flags & 0x0001:
            names.append("Run Immediately")
        if flags & 0x0002:
            names.append("Replace Default")
        flags_text = f"0x{flags:04X}"
        if names:
            flags_text = f"{flags_text} ({', '.join(names)})"
        node.children.append(DetailNode("Script Flags", flags_text))
        node.children.append(DetailNode("Fragment Index", str(fragment)))
        self._attach_validation(node, issues)
        return node

    def _format_epfd_node(
        self,
        field_obj: Field,
        epft_type: Optional[int],
        entry_function: Optional[int],
    ) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if epft_type is None:
            issues.append("EPFD without EPFT")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        effective_type = epft_type
        if epft_type == 2 and entry_function in {5, 12, 13, 14}:
            effective_type = 8
        if effective_type == 0:
            node.value = self._format_numeric(field_obj)
        elif effective_type == 1:
            if len(raw) < 4:
                issues.append(f"EPFD float size {len(raw)} (expected 4)")
                node.value = self._format_numeric(field_obj)
            else:
                value = struct.unpack("<f", raw[0:4])[0]
                node.value = f"{value:.6g}"
        elif effective_type == 2:
            if len(raw) < 8:
                issues.append(f"EPFD float pair size {len(raw)} (expected 8)")
                node.value = self._format_numeric(field_obj)
            else:
                value1 = struct.unpack("<f", raw[0:4])[0]
                value2 = struct.unpack("<f", raw[4:8])[0]
                node.children.append(DetailNode("Float 1", f"{value1:.6g}"))
                node.children.append(DetailNode("Float 2", f"{value2:.6g}"))
        elif effective_type == 3:
            if len(raw) < 4:
                issues.append(f"EPFD LVLI size {len(raw)} (expected 4)")
                node.value = self._format_numeric(field_obj)
            else:
                form_id = int.from_bytes(raw[0:4], "little", signed=False)
                text, refs = self._format_formid_value(form_id, "LVLI")
                node.value = text
                node.refs = refs
                self._validate_formid(form_id, "LVLI", issues, "Leveled Item")
        elif effective_type in {4, 5}:
            if len(raw) < 4:
                issues.append(f"EPFD SPEL size {len(raw)} (expected 4)")
                node.value = self._format_numeric(field_obj)
            else:
                form_id = int.from_bytes(raw[0:4], "little", signed=False)
                text, refs = self._format_formid_value(form_id, "SPEL")
                node.value = text
                node.refs = refs
                self._validate_formid(form_id, "SPEL", issues, "Spell")
        elif effective_type == 6:
            text = decode_text(raw)
            node.value = text if text else self._format_numeric(field_obj)
        elif effective_type == 7:
            text = self._format_localized_or_text(field_obj)
            node.value = text if text is not None else self._format_numeric(field_obj)
        elif effective_type == 8:
            if len(raw) < 8:
                issues.append(f"EPFD AV+Float size {len(raw)} (expected 8)")
                node.value = self._format_numeric(field_obj)
            else:
                actor_value = int.from_bytes(raw[0:4], "little", signed=False)
                value = struct.unpack("<f", raw[4:8])[0]
                node.children.append(DetailNode("Actor Value", str(actor_value)))
                node.children.append(DetailNode("Float", f"{value:.6g}"))
        else:
            issues.append(f"Unknown EPFD type {effective_type}")
            node.value = self._format_numeric(field_obj)
        self._attach_validation(node, issues)
        return node

    def _parse_perk_condition_group(
        self,
        fields: List[Field],
        start_index: int,
    ) -> Tuple[DetailNode, int]:
        field_obj = fields[start_index]
        label = self._field_label(field_obj.signature)
        group = DetailNode("Perk Conditions", "")
        if field_obj.size >= 1:
            run_on = int.from_bytes(field_obj.raw[0:1], "little", signed=True)
            run_on_name = self._run_on_names.get(run_on)
            run_on_text = f"{run_on} ({run_on_name})" if run_on_name else str(run_on)
            group.children.append(DetailNode(label, run_on_text))
        else:
            group.children.append(DetailNode(label, self._format_numeric(field_obj)))
        i = start_index + 1
        last_condition: Optional[DetailNode] = None
        while i < len(fields) and fields[i].signature in {"CTDA", "CIS1", "CIS2", "CITC"}:
            cfield = fields[i]
            if cfield.signature == "CTDA":
                cond_node = self._format_ctda_node(cfield)
                group.children.append(cond_node)
                last_condition = cond_node
            elif cfield.signature in {"CIS1", "CIS2"}:
                text = self._format_localized_or_text(cfield) or self._format_numeric(cfield)
                param_node = DetailNode(self._field_label(cfield.signature), text)
                if last_condition is not None:
                    last_condition.children.append(param_node)
                else:
                    group.children.append(param_node)
            else:
                group.children.append(DetailNode(self._field_label(cfield.signature), self._format_numeric(cfield)))
            i += 1
        return group, i

    def _parse_perk_effect(
        self,
        fields: List[Field],
        start_index: int,
        effect_index: int,
    ) -> Tuple[DetailNode, int]:
        effect_node = DetailNode(f"Effect #{effect_index}", "")
        issues: List[str] = []
        perk_type: Optional[int] = None
        entry_function: Optional[int] = None
        epft_type: Optional[int] = None
        i = start_index
        
        # Look ahead for PRKE to set a better name
        for j in range(start_index, min(start_index + 10, len(fields))):
            if fields[j].signature == "PRKE" and len(fields[j].raw) >= 1:
                ptype = fields[j].raw[0]
                type_name = self._perk_effect_types.get(ptype, f"Type {ptype}")
                effect_node.name = f"Effect: {type_name}"
                break

        while i < len(fields):
            field_obj = fields[i]
            sig = field_obj.signature
            if sig == "PRKE":
                node, perk_type = self._format_prke_header_node(field_obj)
                effect_node.children.append(node)
                i += 1
                continue
            if sig == "DATA":
                node, entry_function = self._format_perk_effect_data_node(field_obj, perk_type)
                effect_node.children.append(node)
                i += 1
                continue
            if sig == "PRKC":
                group, new_index = self._parse_perk_condition_group(fields, i)
                effect_node.children.append(group)
                i = new_index
                continue
            if sig == "EPFT":
                node, epft_type = self._format_epft_node(field_obj)
                effect_node.children.append(node)
                i += 1
                continue
            if sig == "EPF2":
                text = self._format_localized_or_text(field_obj) or self._format_numeric(field_obj)
                effect_node.children.append(DetailNode(self._field_label(sig), text))
                i += 1
                continue
            if sig == "EPF3":
                effect_node.children.append(self._format_epf3_node(field_obj))
                i += 1
                continue
            if sig == "EPFD":
                effect_node.children.append(self._format_epfd_node(field_obj, epft_type, entry_function))
                i += 1
                continue
            if sig == "PRKF":
                effect_node.children.append(self._make_field_node(field_obj))
                i += 1
                break
            effect_node.children.append(self._make_field_node(field_obj))
            i += 1
        if perk_type is None:
            issues.append("Missing PRKE header")
        self._attach_validation(effect_node, issues)
        return effect_node, i

    def _iter_perk_nodes(self) -> List[DetailNode]:
        nodes: List[DetailNode] = []
        fields = self.record.fields
        record_conditions_parent: Optional[DetailNode] = None
        last_record_condition: Optional[DetailNode] = None
        effects_parent: Optional[DetailNode] = None
        effect_index = 0
        i = 0
        while i < len(fields):
            field_obj = fields[i]
            sig = field_obj.signature
            if sig == "CTDA":
                if record_conditions_parent is None:
                    record_conditions_parent = DetailNode("Conditions", "")
                    nodes.append(record_conditions_parent)
                cond_node = self._format_ctda_node(field_obj)
                record_conditions_parent.children.append(cond_node)
                last_record_condition = cond_node
                i += 1
                continue
            if sig in {"CIS1", "CIS2", "CITC"} and record_conditions_parent is not None:
                if sig in {"CIS1", "CIS2"}:
                    text = self._format_localized_or_text(field_obj) or self._format_numeric(field_obj)
                    param_node = DetailNode(self._field_label(sig), text)
                    if last_record_condition is not None:
                        last_record_condition.children.append(param_node)
                    else:
                        record_conditions_parent.children.append(param_node)
                else:
                    record_conditions_parent.children.append(
                        DetailNode(self._field_label(sig), self._format_numeric(field_obj))
                    )
                i += 1
                continue
            if sig == "DATA":
                nodes.append(self._format_perk_main_data_node(field_obj))
                i += 1
                continue
            if sig == "NNAM" and field_obj.size == 4:
                form_id = int.from_bytes(field_obj.raw, "little", signed=False)
                text, refs = self._format_formid_value(form_id, "PERK")
                node = DetailNode(self._field_label(sig), text, refs)
                issues: List[str] = []
                self._validate_formid(form_id, "PERK", issues, "Next Perk")
                self._attach_validation(node, issues)
                nodes.append(node)
                i += 1
                continue
            if sig == "PRKE":
                if effects_parent is None:
                    effects_parent = DetailNode("Effects", "")
                    nodes.append(effects_parent)
                effect_node, new_index = self._parse_perk_effect(fields, i, effect_index)
                effect_index += 1
                effects_parent.children.append(effect_node)
                i = new_index
                continue
            nodes.append(self._make_field_node(field_obj))
            i += 1
        return nodes

    def _format_struct_array(self, field_obj: Field) -> str:
        raw = field_obj.raw
        if len(raw) % 4 != 0 or not raw:
            return self._format_numeric(field_obj)
        values: List[str] = []
        count = len(raw) // 4
        max_preview = min(count, 6)
        for i in range(max_preview):
            chunk = raw[i * 4 : (i + 1) * 4]
            value = int.from_bytes(chunk, "little", signed=False)
            values.append(f"0x{value:08X}")
        text = ", ".join(values)
        if count > max_preview:
            text += f" (+{count - max_preview} more)"
        return text

    def _onam_refs_and_text(self, field_obj: Field) -> Tuple[str, List[Tuple[str, int]]]:
        raw = field_obj.raw
        if len(raw) % 4 != 0:
            return self._format_numeric(field_obj), []
        count = len(raw) // 4
        refs: List[Tuple[str, int]] = []
        if not self.plugin or not self.plugin.formid_resolver:
            preview = min(count, 8)
            parts = []
            for i in range(preview):
                form_id = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little")
                parts.append(f"0x{form_id:08X}")
                refs.append((None, form_id))
            suffix = ", ".join(parts)
            if count > preview:
                suffix += f" (+{count - preview} more)"
            prefix = f"[{count}] " if count else "[0]"
            text = prefix + suffix if suffix else prefix
            return text, refs
        parts: List[str] = []
        preview = min(count, 8)
        for i in range(preview):
            form_id = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little")
            refs.append((None, form_id))
            parts.append(self.plugin.formid_resolver.describe(form_id))
        suffix = ", ".join(parts)
        if count > preview:
            suffix += f" (+{count - preview} more)"
        prefix = f"[{count}] " if count else "[0]"
        text = prefix + suffix if suffix else prefix
        return text, refs

    def _format_tes4_data_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) != 8:
            issues.append(f"Unexpected TES4 DATA size {len(raw)} (expected 8)")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        value = int.from_bytes(raw[:8], "little", signed=False)
        text = "" if value == 0 else f"{value} bytes"
        node.value = text
        self._attach_validation(node, issues)
        return node

    def _format_onam_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        issues: List[str] = []
        if len(raw) % 4 != 0:
            issues.append(f"Unexpected ONAM size {len(raw)}")
            node.value = self._format_numeric(field_obj)
            self._attach_validation(node, issues)
            return node
        count = len(raw) // 4
        node.value = f"[{count}]" if count else "[0]"
        preview = min(count, 8)
        for i in range(preview):
            form_id = int.from_bytes(raw[i * 4 : (i + 1) * 4], "little")
            text, refs = self._format_formid_value(form_id)
            node.children.append(DetailNode(f"Entry {i}", text, refs))
        if count > preview:
            node.children.append(DetailNode("More", f"+{count - preview} entries"))
        self._attach_validation(node, issues)
        return node

    def _format_acbs_node(self, field_obj: Field) -> DetailNode:
        label = self._field_label(field_obj.signature)
        raw = field_obj.raw
        node = DetailNode(label, "")
        if len(raw) < 24:
            node.value = self._format_numeric(field_obj)
            return node

        flags = int.from_bytes(raw[0:4], "little", signed=False)
        magicka_offset = int.from_bytes(raw[4:6], "little", signed=True)
        stamina_offset = int.from_bytes(raw[6:8], "little", signed=True)
        level_raw = int.from_bytes(raw[8:10], "little", signed=False)
        min_level = int.from_bytes(raw[10:12], "little", signed=False)
        max_level = int.from_bytes(raw[12:14], "little", signed=False)
        speed_mult = int.from_bytes(raw[14:16], "little", signed=False)
        disp_base = int.from_bytes(raw[16:18], "little", signed=False)
        template_flags = int.from_bytes(raw[18:20], "little", signed=False)
        health_offset = int.from_bytes(raw[20:22], "little", signed=True)
        bleedout_override = int.from_bytes(raw[22:24], "little", signed=False)

        pc_level_mult = bool(flags & 0x80)
        level_value = level_raw / 1000.0 if pc_level_mult and level_raw else level_raw

        node.children.append(DetailNode("Flags", f"0x{flags:08X}"))
        node.children.append(DetailNode("Level", f"{level_value:g} (min {min_level}, max {max_level})"))
        node.children.append(DetailNode("Speed Mult", str(speed_mult)))
        node.children.append(DetailNode("Disposition", str(disp_base)))
        node.children.append(DetailNode("Template Flags", f"0x{template_flags:04X}"))
        node.children.append(DetailNode("Magicka Offset", str(magicka_offset)))
        node.children.append(DetailNode("Stamina Offset", str(stamina_offset)))
        node.children.append(DetailNode("Health Offset", str(health_offset)))
        node.children.append(DetailNode("Bleedout Override", str(bleedout_override)))
        
        node.value = f"Level {level_value:g}, Flags 0x{flags:08X}"
        return node

    def _format_acbs(self, field_obj: Field) -> str:
        raw = field_obj.raw
        if len(raw) < 24:
            return self._format_numeric(field_obj)
        flags = int.from_bytes(raw[0:4], "little", signed=False)
        magicka_offset = int.from_bytes(raw[4:6], "little", signed=True)
        stamina_offset = int.from_bytes(raw[6:8], "little", signed=True)
        level_raw = int.from_bytes(raw[8:10], "little", signed=False)
        min_level = int.from_bytes(raw[10:12], "little", signed=False)
        max_level = int.from_bytes(raw[12:14], "little", signed=False)
        speed_mult = int.from_bytes(raw[14:16], "little", signed=False)
        disp_base = int.from_bytes(raw[16:18], "little", signed=False)
        template_flags = int.from_bytes(raw[18:20], "little", signed=False)
        health_offset = int.from_bytes(raw[20:22], "little", signed=True)
        bleedout_override = int.from_bytes(raw[22:24], "little", signed=False)

        pc_level_mult = bool(flags & 0x80)
        level_value = level_raw / 1000.0 if pc_level_mult and level_raw else level_raw

        parts: List[str] = []
        parts.append(f"Flags: 0x{flags:08X}")
        parts.append(f"Level: {level_value:g} (min {min_level}, max {max_level})")
        parts.append(f"Speed Mult: {speed_mult}")
        parts.append(f"Disposition: {disp_base}")
        parts.append(f"Template Flags: 0x{template_flags:04X}")
        parts.append(f"Magicka Offset: {magicka_offset}")
        parts.append(f"Stamina Offset: {stamina_offset}")
        parts.append(f"Health Offset: {health_offset}")
        parts.append(f"Bleedout Override: {bleedout_override}")
        return "; ".join(parts)

    def _format_tnam(self, field_obj: Field) -> str:
        if field_obj.size != 4:
            return self._format_numeric(field_obj)
        value = int.from_bytes(field_obj.raw, "little", signed=False)
        return f"0x{value:08X} ({value})"

    def _read_u8(self, raw: bytes, pos: int) -> Tuple[Optional[int], int, Optional[str]]:
        if pos + 1 > len(raw):
            return None, pos, "Unexpected end of VMAD data"
        return raw[pos], pos + 1, None

    def _read_u16(self, raw: bytes, pos: int) -> Tuple[Optional[int], int, Optional[str]]:
        if pos + 2 > len(raw):
            return None, pos, "Unexpected end of VMAD data"
        value = int.from_bytes(raw[pos : pos + 2], "little", signed=False)
        return value, pos + 2, None

    def _read_i16(self, raw: bytes, pos: int) -> Tuple[Optional[int], int, Optional[str]]:
        if pos + 2 > len(raw):
            return None, pos, "Unexpected end of VMAD data"
        value = int.from_bytes(raw[pos : pos + 2], "little", signed=True)
        return value, pos + 2, None

    def _read_u32(self, raw: bytes, pos: int) -> Tuple[Optional[int], int, Optional[str]]:
        if pos + 4 > len(raw):
            return None, pos, "Unexpected end of VMAD data"
        value = int.from_bytes(raw[pos : pos + 4], "little", signed=False)
        return value, pos + 4, None

    def _read_f32(self, raw: bytes, pos: int) -> Tuple[Optional[float], int, Optional[str]]:
        if pos + 4 > len(raw):
            return None, pos, "Unexpected end of VMAD data"
        value = struct.unpack_from("<f", raw, pos)[0]
        return value, pos + 4, None

    def _read_bstring(self, raw: bytes, pos: int) -> Tuple[Optional[str], int, Optional[str]]:
        """Читает строку формата uint16_length + char[length] (ASCII/UTF-8).

        Это формат хранения строк в VMAD (Papyrus), НЕ UTF-16.
        """
        length, pos, error = self._read_u16(raw, pos)
        if error or length is None:
            return None, pos, error
        if pos + length > len(raw):
            return None, pos, "Unexpected end of VMAD string data"
        text = raw[pos : pos + length].decode("utf-8", errors="replace")
        return text, pos + length, None

    def _format_vmad_node(self, field_obj: Field) -> DetailNode:
        """Создает иерархическую структуру DetailNode для VMAD."""
        raw = field_obj.raw
        pos = 0
        refs: List[Tuple[Optional[str], int]] = []

        version, pos, error = self._read_i16(raw, pos)
        if error or version is None:
            return DetailNode("VMAD", self._format_numeric(field_obj))
        obj_format, pos, error = self._read_i16(raw, pos)
        if error or obj_format is None:
            return DetailNode("VMAD", self._format_numeric(field_obj))
        script_count, pos, error = self._read_u16(raw, pos)
        if error or script_count is None:
            return DetailNode("VMAD", self._format_numeric(field_obj))

        # Корневой узел VMAD
        vmad_node = DetailNode("VMAD - Virtual Machine Adapter (Scripts)", f"Version: {version}, ObjFormat: {obj_format}")
        scripts_node = DetailNode("Scripts", f"Count: {script_count}")
        vmad_node.children.append(scripts_node)

        for i in range(script_count):
            script_name, pos, error = self._read_bstring(raw, pos)
            if error or script_name is None:
                break
            
            script_info = f"{script_name}"
            if version >= 4:
                # Inherited flag (u8)
                inherited, pos, error = self._read_u8(raw, pos)
                if not error:
                    script_info += f" (Inherited: {inherited})"

            property_count, pos, error = self._read_u16(raw, pos)
            if error or property_count is None:
                break
            
            script_item_node = DetailNode(script_name, script_info)
            scripts_node.children.append(script_item_node)
            
            if property_count > 0:
                props_node = DetailNode("Properties", f"Count: {property_count}")
                script_item_node.children.append(props_node)

                for j in range(property_count):
                    prop_name, pos, error = self._read_bstring(raw, pos)
                    if error or prop_name is None:
                        break
                    prop_type, pos, error = self._read_u8(raw, pos)
                    if error or prop_type is None:
                        break
                    
                    prop_status_val = None
                    prop_status_str = ""
                    if version >= 4:
                        prop_status_val, pos, error = self._read_u8(raw, pos)
                        if not error:
                            prop_status_str = f" (Status: {prop_status_val})"

                    prop_value_str = "Unknown Type"
                    prop_refs: List[Tuple[Optional[str], int]] = []

                    # Обработка типов данных (аналогично _format_vmad)
                    if prop_type in {1, 11}: # Object / Object Array
                        count = 1
                        if prop_type == 11:
                            count, pos, error = self._read_u32(raw, pos)
                            if error or count is None: break
                        
                        vals = []
                        for _ in range(count):
                            if obj_format == 1 or (obj_format == 2 and version < 4):
                                if pos + 4 > len(raw): break
                                form_id = int.from_bytes(raw[pos : pos + 4], "little", signed=False)
                                pos += 4
                            else:
                                if pos + 8 > len(raw): break
                                form_id = int.from_bytes(raw[pos + 4 : pos + 8], "little", signed=False)
                                pos += 8
                            if form_id:
                                prop_refs.append((None, form_id))
                                vals.append(f"0x{form_id:08X}")
                            else:
                                vals.append("None")
                        prop_value_str = ", ".join(vals)

                    elif prop_type in {2, 12}: # String / String Array
                        count = 1
                        if prop_type == 12:
                            count, pos, error = self._read_u32(raw, pos)
                            if error or count is None: break
                        vals = []
                        for _ in range(count):
                            val, pos, error = self._read_bstring(raw, pos)
                            if error: break
                            vals.append(f'"{val}"')
                        prop_value_str = ", ".join(vals)

                    elif prop_type in {3, 13}: # Int / Int Array
                        count = 1
                        if prop_type == 13:
                            count, pos, error = self._read_u32(raw, pos)
                            if error or count is None: break
                        vals = []
                        for _ in range(count):
                            if pos + 4 > len(raw): break
                            val = int.from_bytes(raw[pos:pos+4], "little", signed=True)
                            pos += 4
                            vals.append(str(val))
                        prop_value_str = ", ".join(vals)

                    elif prop_type in {4, 14}: # Float / Float Array
                        count = 1
                        if prop_type == 14:
                            count, pos, error = self._read_u32(raw, pos)
                            if error or count is None: break
                        vals = []
                        for _ in range(count):
                            val, pos, error = self._read_f32(raw, pos)
                            if error: break
                            vals.append(f"{val:.6f}")
                        prop_value_str = ", ".join(vals)

                    elif prop_type in {5, 15}: # Bool / Bool Array
                        count = 1
                        if prop_type == 15:
                            count, pos, error = self._read_u32(raw, pos)
                            if error or count is None: break
                        vals = []
                        for _ in range(count):
                            if pos + 1 > len(raw): break
                            val = raw[pos] != 0
                            pos += 1
                            vals.append("True" if val else "False")
                        prop_value_str = ", ".join(vals)
                    
                    prop_node = DetailNode(prop_name, prop_value_str, prop_refs)
                    props_node.children.append(prop_node)

        if pos < len(raw):
            vmad_node.children.append(DetailNode("Fragments/Extra", f"{len(raw) - pos} bytes"))

        return vmad_node

    def _format_vmad(self, field_obj: Field) -> Tuple[str, List[Tuple[str, int]]]:
        raw = field_obj.raw
        pos = 0
        refs: List[Tuple[str, int]] = []

        version, pos, error = self._read_i16(raw, pos)
        if error or version is None:
            return self._format_numeric(field_obj), refs
        obj_format, pos, error = self._read_i16(raw, pos)
        if error or obj_format is None:
            return self._format_numeric(field_obj), refs
        script_count, pos, error = self._read_u16(raw, pos)
        if error or script_count is None:
            return self._format_numeric(field_obj), refs

        scripts: List[str] = []
        property_total = 0
        max_script_preview = 4
        max_prop_preview = 8
        preview_props: List[str] = []

        for _ in range(script_count):
            script_name, pos, error = self._read_bstring(raw, pos)
            if error or script_name is None:
                return self._format_numeric(field_obj), refs
            if len(scripts) < max_script_preview:
                scripts.append(script_name)
            if version >= 4:
                _, pos, error = self._read_u8(raw, pos)
                if error:
                    return self._format_numeric(field_obj), refs
            property_count, pos, error = self._read_u16(raw, pos)
            if error or property_count is None:
                return self._format_numeric(field_obj), refs
            property_total += property_count

            for _ in range(property_count):
                prop_name, pos, error = self._read_bstring(raw, pos)
                if error or prop_name is None:
                    return self._format_numeric(field_obj), refs
                prop_type, pos, error = self._read_u8(raw, pos)
                if error or prop_type is None:
                    return self._format_numeric(field_obj), refs
                if version >= 4:
                    _, pos, error = self._read_u8(raw, pos)
                    if error:
                        return self._format_numeric(field_obj), refs

                if prop_type in {1, 11}:
                    count = 1
                    if prop_type == 11:
                        count, pos, error = self._read_u32(raw, pos)
                        if error or count is None:
                            return self._format_numeric(field_obj), refs
                    for _ in range(count):
                        if obj_format == 1 or (obj_format == 2 and version < 4):
                            if pos + 4 > len(raw):
                                return self._format_numeric(field_obj), refs
                            form_id = int.from_bytes(raw[pos : pos + 4], "little", signed=False)
                            pos += 4
                        else:
                            if pos + 8 > len(raw):
                                return self._format_numeric(field_obj), refs
                            form_id = int.from_bytes(raw[pos + 4 : pos + 8], "little", signed=False)
                            pos += 8
                        if form_id:
                            refs.append((None, form_id))
                            if len(preview_props) < max_prop_preview:
                                preview_props.append(f"{prop_name} -> 0x{form_id:08X}")
                    continue

                if prop_type in {2, 12}:
                    count = 1
                    if prop_type == 12:
                        count, pos, error = self._read_u32(raw, pos)
                        if error or count is None:
                            return self._format_numeric(field_obj), refs
                    for _ in range(count):
                        _, pos, error = self._read_bstring(raw, pos)
                        if error:
                            return self._format_numeric(field_obj), refs
                    continue

                if prop_type in {3, 13}:
                    count = 1
                    if prop_type == 13:
                        count, pos, error = self._read_u32(raw, pos)
                        if error or count is None:
                            return self._format_numeric(field_obj), refs
                    pos += 4 * count
                    if pos > len(raw):
                        return self._format_numeric(field_obj), refs
                    continue

                if prop_type in {4, 14}:
                    count = 1
                    if prop_type == 14:
                        count, pos, error = self._read_u32(raw, pos)
                        if error or count is None:
                            return self._format_numeric(field_obj), refs
                    pos += 4 * count
                    if pos > len(raw):
                        return self._format_numeric(field_obj), refs
                    continue

                if prop_type in {5, 15}:
                    count = 1
                    if prop_type == 15:
                        count, pos, error = self._read_u32(raw, pos)
                        if error or count is None:
                            return self._format_numeric(field_obj), refs
                    pos += count
                    if pos > len(raw):
                        return self._format_numeric(field_obj), refs
                    continue

                return self._format_numeric(field_obj), refs

        info = f"Version: {version}, ObjFormat: {obj_format}, Scripts: {script_count}, Properties: {property_total}"
        if scripts:
            preview = ", ".join(scripts)
            if script_count > len(scripts):
                preview += f" (+{script_count - len(scripts)} more)"
            info += f"; Script Names: {preview}"
        if preview_props:
            info += f"; Props: {', '.join(preview_props)}"
        if pos < len(raw):
            info += f"; Fragments/Extra: {len(raw) - pos} bytes"

        return info, refs

    def format_field(self, field_obj: Field) -> str:
        sig = field_obj.signature

        if sig in {"EDID", "FULL", "DESC", "CNAM", "SNAM", "ANAM", "RNAM", "QNAM"}:
            text = self._format_localized_or_text(field_obj)
            if text is not None:
                return text

        text_sigs = {
            "MODL",
            "MOD2",
            "MOD3",
            "MOD4",
            "MOD5",
            "ICON",
            "MICO",
            "NAM1",
            "NAM2",
            "ALID",
            "ATKE",
            "UNAM",
            "TINT",
        }
        if sig in text_sigs:
            text = self._format_text_candidate(field_obj)
            if text is not None:
                return text

        if sig == "MODT":
            return f"{field_obj.size} bytes"

        if sig == "KWDA":
            return self._format_kwda(field_obj)

        if sig == "MAST":
            return self._format_mast(field_obj)

        if sig == "ONAM":
            text, _ = self._onam_refs_and_text(field_obj)
            return text

        if sig == "TNAM":
            return self._format_tnam(field_obj)

        if sig == "VMAD":
            text, _ = self._format_vmad(field_obj)
            return text

        if sig == "ACBS":
            return self._format_acbs(field_obj)

        if sig in {"DATA", "DNAM", "SNDD", "MDOB"}:
            return self._format_struct_array(field_obj)

        return self._format_numeric(field_obj)

    def _make_field_node(self, field_obj: Field) -> DetailNode:
        sig = field_obj.signature
        if not self._is_known_field_signature(sig):
            label = f"{sig} - Unknown"
            return DetailNode(label, self._format_unknown_value(field_obj))
        label = self._field_label(sig)
        refs: List[Tuple[Optional[str], int]] = []
        if sig == "KWDA":
            value, refs = self._kwda_refs_and_text(field_obj)
        elif sig == "VMAD":
            return self._format_vmad_node(field_obj)
        elif sig == "ACBS":
            return self._format_acbs_node(field_obj)
        elif sig == "ONAM":
            value, refs = self._onam_refs_and_text(field_obj)
        elif sig == "EFID" and field_obj.size == 4:
            form_id = int.from_bytes(field_obj.raw, "little", signed=False)
            value, refs = self._format_formid_value(form_id, "MGEF")
        elif sig == "NNAM" and field_obj.size == 4:
            form_id = int.from_bytes(field_obj.raw, "little", signed=False)
            value, refs = self._format_formid_value(form_id, "PERK")
        else:
            value = self.format_field(field_obj)
        return DetailNode(label, value, refs)

    def iter_nodes(self) -> List[DetailNode]:
        nodes: List[DetailNode] = [self.get_record_header_node()]
        if self.record.signature == "PERK":
            try:
                nodes.extend(self._iter_perk_nodes())
                return nodes
            except Exception:
                self._logger.exception(f"Failed to parse PERK record {self.record.form_id:08X}")
                nodes.extend(self._make_field_node(field) for field in self.record.fields)
                return nodes
        fields = self.record.fields
        effects_parent: Optional[DetailNode] = None
        effect_index = 0
        record_conditions_parent: Optional[DetailNode] = None
        last_record_condition: Optional[DetailNode] = None
        i = 0

        while i < len(fields):
            field_obj = fields[i]
            sig = field_obj.signature

            if self.record.signature in {"SPEL", "ENCH"} and sig == "EFID":
                if effects_parent is None:
                    effects_parent = DetailNode("Effects", "")
                    nodes.append(effects_parent)
                effect_node = DetailNode(f"Effect #{effect_index}", "")
                
                # Get effect name for stable key
                effect_name = "Unknown Effect"
                if field_obj.size == 4:
                    mgef_id = int.from_bytes(field_obj.raw, "little", signed=False)
                    if self.plugin and self.plugin.formid_resolver:
                        effect_name = self.plugin.formid_resolver.describe(mgef_id)
                    else:
                        effect_name = f"0x{mgef_id:08X}"
                
                effect_node.name = f"Effect: {effect_name}"
                effect_index += 1
                effects_parent.children.append(effect_node)
                effect_node.children.append(self._make_field_node(field_obj))

                if i + 1 < len(fields) and fields[i + 1].signature == "EFIT":
                    effect_node.children.append(self._format_efit_node(fields[i + 1]))
                    i += 1

                cond_parent: Optional[DetailNode] = None
                last_effect_condition: Optional[DetailNode] = None
                while i + 1 < len(fields) and fields[i + 1].signature in {"CTDA", "CIS1", "CIS2", "CITC"}:
                    i += 1
                    cfield = fields[i]
                    if cfield.signature == "CTDA":
                        if cond_parent is None:
                            cond_parent = DetailNode("Conditions", "")
                        cond_node = self._format_ctda_node(cfield)
                        cond_parent.children.append(cond_node)
                        last_effect_condition = cond_node
                        continue
                    if cfield.signature in {"CIS1", "CIS2"}:
                        text = self._format_localized_or_text(cfield) or self._format_numeric(cfield)
                        param_node = DetailNode(self._field_label(cfield.signature), text)
                        if last_effect_condition is not None:
                            last_effect_condition.children.append(param_node)
                        else:
                            if cond_parent is None:
                                cond_parent = DetailNode("Conditions", "")
                            cond_parent.children.append(param_node)
                        continue
                    if cfield.signature == "CITC":
                        if cond_parent is None:
                            cond_parent = DetailNode("Conditions", "")
                        cond_parent.children.append(
                            DetailNode(self._field_label(cfield.signature), self._format_numeric(cfield))
                        )

                if cond_parent is not None:
                    effect_node.children.append(cond_parent)
                i += 1
                continue

            if sig == "CTDA":
                if record_conditions_parent is None:
                    record_conditions_parent = DetailNode("Conditions", "")
                    nodes.append(record_conditions_parent)
                cond_node = self._format_ctda_node(field_obj)
                record_conditions_parent.children.append(cond_node)
                last_record_condition = cond_node
                i += 1
                continue

            if sig in {"CIS1", "CIS2", "CITC"} and record_conditions_parent is not None:
                if sig in {"CIS1", "CIS2"}:
                    text = self._format_localized_or_text(field_obj) or self._format_numeric(field_obj)
                    param_node = DetailNode(self._field_label(sig), text)
                    if last_record_condition is not None:
                        last_record_condition.children.append(param_node)
                    else:
                        record_conditions_parent.children.append(param_node)
                else:
                    record_conditions_parent.children.append(
                        DetailNode(self._field_label(sig), self._format_numeric(field_obj))
                    )
                i += 1
                continue

            if sig == "VMAD":
                nodes.append(self._format_vmad_node(field_obj))
                i += 1
                continue

            if sig == "HEDR":
                nodes.append(self._format_hedr_node(field_obj))
                i += 1
                continue

            if sig == "ONAM":
                nodes.append(self._format_onam_node(field_obj))
                i += 1
                continue

            if sig == "OBND":
                nodes.append(self._format_obnd_node(field_obj))
                i += 1
                continue

            if sig == "SPIT":
                nodes.append(self._format_spit_node(field_obj))
                i += 1
                continue

            if sig == "XCLC":
                nodes.append(self._format_xclc_node(field_obj))
                i += 1
                continue

            if sig == "XPRM" and self.record.signature == "REFR":
                nodes.append(self._format_xprm_node(field_obj))
                i += 1
                continue

            if sig == "XMBO" and self.record.signature == "REFR":
                nodes.append(self._format_xmbo_node(field_obj))
                i += 1
                continue

            if self.record.signature == "LAND":
                if sig == "VNML":
                    nodes.append(self._format_land_vnml_node(field_obj))
                    i += 1
                    continue
                if sig == "VHGT":
                    nodes.append(self._format_land_vhgt_node(field_obj))
                    i += 1
                    continue
                if sig == "VTXT":
                    nodes.append(self._format_land_vtxt_node(field_obj))
                    i += 1
                    continue
                if sig == "VCLR":
                    nodes.append(self._format_land_vclr_node(field_obj))
                    i += 1
                    continue

            if sig == "DATA" and self.record.signature in {"REFR", "ACHR", "ACRE"}:
                nodes.append(self._format_ref_data_node(field_obj))
                i += 1
                continue

            if sig == "DATA" and self.record.signature == "TES4":
                nodes.append(self._format_tes4_data_node(field_obj))
                i += 1
                continue

            if sig == "DATA" and self.record.signature == "DIAL":
                nodes.append(self._format_dial_data_node(field_obj))
                i += 1
                continue

            if sig == "TRDT" and self.record.signature == "INFO":
                nodes.append(self._format_info_trdt_node(field_obj))
                i += 1
                continue

            if sig == "DATA" and self.record.signature == "MGEF":
                nodes.append(self._format_mgef_data_node(field_obj))
                i += 1
                continue

            if sig == "DATA" and self.record.signature == "GMST":
                nodes.append(self._format_gmst_data_node(field_obj))
                i += 1
                continue

            if sig in {"INTV", "INCC"} and self.record.signature == "TES4":
                if field_obj.size < 4:
                    nodes.append(DetailNode(self._field_label(sig), self._format_numeric(field_obj)))
                else:
                    text = str(int.from_bytes(field_obj.raw[:4], "little", signed=False))
                    nodes.append(DetailNode(self._field_label(sig), text))
                i += 1
                continue

            if sig == "CNAM" and self.record.signature == "KYWD":
                nodes.append(self._format_rgba_node(field_obj))
                i += 1
                continue

            if sig == "MHDT" and self.record.signature == "WRLD":
                nodes.append(self._format_wrld_mhdt_node(field_obj))
                i += 1
                continue

            if sig == "MHDT" and self.record.signature == "CELL":
                nodes.append(self._format_cell_mhdt_node(field_obj))
                i += 1
                continue

            if sig == "RNAM" and self.record.signature == "WRLD":
                nodes.append(self._format_rnam_node(field_obj))
                i += 1
                continue

            if sig == "XLIG" and self.record.signature == "REFR":
                nodes.append(self._format_xlig_node(field_obj))
                i += 1
                continue

            if sig == "XRGD" and self.record.signature == "REFR":
                nodes.append(self._format_xrgd_node(field_obj))
                i += 1
                continue

            if sig == "PKDT" and self.record.signature == "PACK":
                nodes.append(self._format_pkdt_node(field_obj))
                i += 1
                continue

            if sig == "PSDT" and self.record.signature == "PACK":
                nodes.append(self._format_psdt_node(field_obj))
                i += 1
                continue

            if sig == "PKCU" and self.record.signature == "PACK":
                nodes.append(self._format_pkcu_node(field_obj))
                i += 1
                continue

            if sig == "AIDT" and self.record.signature in {"NPC_", "CREA"}:
                nodes.append(self._format_aidt_node(field_obj))
                i += 1
                continue

            if sig == "ATKD" and self.record.signature in {"NPC_", "CREA"}:
                nodes.append(self._format_atkd_node(field_obj))
                i += 1
                continue

            if sig == "DATA" and self.record.signature == "IDLE":
                nodes.append(self._format_idle_data_node(field_obj))
                i += 1
                continue

            if sig == "BNAM" and self.record.signature == "SNDR":
                nodes.append(self._format_sndr_bnam_node(field_obj))
                i += 1
                continue

            if sig in {"NVMI", "NVNM"}:
                if sig == "NVMI":
                    nodes.append(self._format_nvmi_node(field_obj))
                else:
                    nodes.append(self._format_nvnm_node(field_obj))
                i += 1
                continue

            if sig == "PTDA" and self.record.signature == "PACK":
                nodes.append(self._format_ptda_node(field_obj))
                i += 1
                continue

            if sig == "LLCT" and self.record.signature in {"LVLI", "LVLN", "LVSP"}:
                nodes.append(self._format_llct_node(field_obj))
                i += 1
                continue

            if sig == "LVLO" and self.record.signature in {"LVLI", "LVLN", "LVSP"}:
                nodes.append(self._format_lvlo_node(field_obj))
                i += 1
                continue

            if self.record.signature == "WEAP":
                if sig == "DATA":
                    nodes.append(self._format_weap_data_node(field_obj))
                    i += 1
                    continue
                if sig == "DNAM":
                    nodes.append(self._format_weap_dnam_node(field_obj))
                    i += 1
                    continue
                if sig == "CRDT":
                    nodes.append(self._format_weap_crdt_node(field_obj))
                    i += 1
                    continue

            if self.record.signature == "ARMO":
                if sig == "DATA":
                    nodes.append(self._format_armo_data_node(field_obj))
                    i += 1
                    continue
                if sig == "DNAM":
                    nodes.append(self._format_armo_dnam_node(field_obj))
                    i += 1
                    continue
                if sig == "BOD2":
                    nodes.append(self._format_biped_object_node(field_obj))
                    i += 1
                    continue

            if self.record.signature == "ARMA":
                if sig in {"BOD2", "BODT"}:
                    nodes.append(self._format_biped_object_node(field_obj))
                    i += 1
                    continue

            if self.record.signature == "RACE":
                if sig in {"BOD2", "BODT"}:
                    nodes.append(self._format_biped_object_node(field_obj))
                    i += 1
                    continue

            if sig == "CNAM":
                nodes.append(self._format_generic_formid_node(field_obj))
                i += 1
                continue
            if sig == "RNAM":
                # В INFO это число, в других может быть FormID. Проверим размер.
                if self.record.signature == "INFO" and len(field_obj.raw) <= 4:
                    nodes.append(DetailNode(self._field_label("RNAM"), str(int.from_bytes(field_obj.raw, "little"))))
                else:
                    nodes.append(self._format_generic_formid_node(field_obj))
                i += 1
                continue
            if sig == "ANAM":
                # В PACK это FormID, в других может быть структура.
                if self.record.signature == "PACK" and len(field_obj.raw) == 4:
                    nodes.append(self._format_generic_formid_node(field_obj))
                else:
                    nodes.append(DetailNode(self._field_label("ANAM"), self._format_numeric(field_obj)))
                i += 1
                continue
            if sig == "NAM2":
                # Hazard Data в HAZD — обычно структура, но может быть FormID.
                nodes.append(DetailNode(self._field_label("NAM2"), self._format_numeric(field_obj)))
                i += 1
                continue

            if self.record.signature == "BOOK" and sig == "DATA":
                nodes.append(self._format_book_data_node(field_obj))
                i += 1
                continue

            if self.record.signature == "ALCH" and sig == "DATA":
                nodes.append(self._format_alch_data_node(field_obj))
                i += 1
                continue

            if self.record.signature == "AMMO" and sig == "DATA":
                nodes.append(self._format_ammo_data_node(field_obj))
                i += 1
                continue

            if self.record.signature == "MISC" and sig == "DATA":
                nodes.append(self._format_misc_data_node(field_obj))
                i += 1
                continue

            if sig in {"DATA", "DNAM", "MDOB"}:
                nodes.append(self._format_struct_array_node(field_obj))
                i += 1
                continue

            if sig == "SNDD":
                nodes.append(self._format_sndd_node(field_obj))
                i += 1
                continue

            if sig == "EFIT":
                nodes.append(self._format_efit_node(field_obj))
                i += 1
                continue

            nodes.append(self._make_field_node(field_obj))
            i += 1

        return nodes
