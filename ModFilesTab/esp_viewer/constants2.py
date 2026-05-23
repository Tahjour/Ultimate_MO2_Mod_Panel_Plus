"""
constants.py — полный набор констант, сигнатур, меток, флагов и перечислений
для парсинга плагинов Skyrim Special Edition (TES5/SSE).
"""

from enum import IntEnum, IntFlag
from typing import Dict, FrozenSet, Set, Tuple

MAX_FIELD_PREVIEW_BYTES = 64

# ─────────────────────────────────────────────────────────
# 1. LOCALIZED SIGNATURES
#    Субрекорды, которые при включённом флаге Localized
#    содержат uint32 (lstring index) вместо raw-строки.
# ─────────────────────────────────────────────────────────
LOCALIZED_SIGNATURES: FrozenSet[str] = frozenset({
    "FULL",   # Display Name
    "DESC",   # Description
    "SHRT",   # Short Name
    "TNAM",   # Text (context-dependent)
    "ITXT",   # Icon Text / Button Text
    "NNAM",   # Notification text / response text
    "CNAM",   # Author / text (context-dependent)
    "SNAM",   # Description / subtitle (context-dependent)
    "ANAM",   # Attenuation / text (context-dependent)
    "RNAM",   # Prompt / text (context-dependent)
    "QNAM",   # Quest text (context-dependent)
    "DNAM",   # Data text (context-dependent, in some records)
    "EPFD",   # Entry Point Function Data (for perk text)
    "NAM1",   # Dialog response text
})

# ─────────────────────────────────────────────────────────
# 2. RECORD SIGNATURES — все типы записей Skyrim SE
# ─────────────────────────────────────────────────────────
RECORD_SIGNATURE_TYPES: Dict[str, str] = {
    # === File / Group structure ===
    "TES4": "File Header",
    "GRUP": "Group",

    # === Game meta ===
    "GMST": "Game Setting",
    "KYWD": "Keyword",
    "LCRT": "Location Ref Type",
    "AACT": "Action",
    "TXST": "Texture Set",
    "GLOB": "Global",
    "CLAS": "Class",
    "FACT": "Faction",
    "HDPT": "Head Part",
    "EYES": "Eyes",
    "RACE": "Race",
    "SOUN": "Sound Marker",
    "ASPC": "Acoustic Space",
    "MGEF": "Magic Effect",
    "SCPT": "Script (Deprecated)",
    "LTEX": "Land Texture",
    "ENCH": "Object Effect (Enchantment)",
    "SPEL": "Spell",
    "SCRL": "Scroll",

    # === World Objects ===
    "ACTI": "Activator",
    "TACT": "Talking Activator",
    "ARMO": "Armor",
    "BOOK": "Book",
    "CONT": "Container",
    "DOOR": "Door",
    "INGR": "Ingredient",
    "LIGH": "Light",
    "MISC": "Misc Item",
    "APPA": "Apparatus",
    "STAT": "Static",
    "MSTT": "Moveable Static",
    "GRAS": "Grass",
    "TREE": "Tree",
    "FLOR": "Flora",
    "FURN": "Furniture",
    "WEAP": "Weapon",
    "AMMO": "Ammunition",
    "NPC_": "Non-Player Character",
    "LVLN": "Leveled NPC",
    "KEYM": "Key",
    "ALCH": "Ingestible (Potion)",
    "IDLM": "Idle Marker",
    "COBJ": "Constructible Object",
    "PROJ": "Projectile",
    "HAZD": "Hazard",
    "SLGM": "Soul Gem",
    "LVLI": "Leveled Item",

    # === Environment ===
    "WTHR": "Weather",
    "CLMT": "Climate",
    "SPGD": "Shader Particle Geometry",
    "RFCT": "Visual Effect",
    "REGN": "Region",
    "NAVI": "Navigation Mesh Info Map",

    # === World / Cell ===
    "CELL": "Cell",
    "REFR": "Placed Object",
    "ACHR": "Placed NPC",
    "PMIS": "Placed Missile",
    "PGRE": "Placed Grenade (Arrow)",
    "PHZD": "Placed Hazard",
    "WRLD": "Worldspace",
    "LAND": "Landscape",
    "NAVM": "Navigation Mesh",

    # === Dialog / Quest ===
    "DIAL": "Dialog Topic",
    "INFO": "Dialog Info (Response)",
    "QUST": "Quest",

    # === AI / Animation ===
    "IDLE": "Idle Animation",
    "PACK": "AI Package",
    "CSTY": "Combat Style",

    # === UI / Misc ===
    "LSCR": "Load Screen",
    "LVSP": "Leveled Spell",
    "ANIO": "Animated Object",
    "WATR": "Water Type",
    "EFSH": "Effect Shader",
    "EXPL": "Explosion",
    "DEBR": "Debris",
    "IMGS": "Image Space",
    "IMAD": "Image Space Adapter",
    "FLST": "FormID List",
    "PERK": "Perk",
    "BPTD": "Body Part Data",
    "ADDN": "Addon Node",
    "AVIF": "Actor Value Info",
    "CAMS": "Camera Shot",
    "CPTH": "Camera Path",
    "VTYP": "Voice Type",
    "MATT": "Material Type",
    "IPCT": "Impact",
    "IPDS": "Impact Data Set",
    "ARMA": "Armor Addon",
    "ECZN": "Encounter Zone",
    "LCTN": "Location",
    "MESG": "Message",
    "DOBJ": "Default Object Manager",
    "LGTM": "Lighting Template",
    "MUSC": "Music Type",
    "FSTP": "Footstep",
    "FSTS": "Footstep Set",
    "SMBN": "Story Manager Branch Node",
    "SMQN": "Story Manager Quest Node",
    "SMEN": "Story Manager Event Node",
    "DLBR": "Dialog Branch",
    "MUST": "Music Track",
    "DLVW": "Dialog View",
    "WOOP": "Word of Power",
    "SHOU": "Shout",
    "EQUP": "Equip Type",
    "RELA": "Relationship",
    "SCEN": "Scene",
    "ASTP": "Association Type",
    "OTFT": "Outfit",
    "ARTO": "Art Object",
    "MATO": "Material Object",
    "MOVT": "Movement Type",
    "SNDR": "Sound Descriptor",
    "DUAL": "Dual Cast Data",
    "SNCT": "Sound Category",
    "SOPM": "Sound Output Model",
    "COLL": "Collision Layer",
    "CLFM": "Color",
    "REVB": "Reverb Parameters",
    "LENS": "Lens Flare",
    "VOLI": "Volumetric Lighting",

    # === SSE-only / SKSE-adjacent ===
    "RFGP": "Reference Group",  # SSE only (rare)
}

# ─────────────────────────────────────────────────────────
# 3. SUBRECORD LABELS  (полный справочник)
# ─────────────────────────────────────────────────────────
SUBRECORD_LABELS: Dict[str, str] = {
    # ── Универсальные / общие ──
    "EDID": "Editor ID",
    "FULL": "Display Name",
    "DESC": "Description",
    "DATA": "Data",
    "DNAM": "Data (Named)",
    "XNAM": "Data (Extra)",
    "FNAM": "Flags",
    "PNAM": "Previous / Parent",
    "HNAM": "Hair / Handle",

    # ── Модели ──
    "MODL": "Model Filename",
    "MODT": "Model Texture File Hashes",
    "MODS": "Model Alternate Textures",
    "MODF": "Model Flags",                # SSE
    "MOD2": "Female Model Filename",
    "MO2T": "Female Model Texture Hashes",
    "MO2S": "Female Model Alt Textures",
    "MOD3": "Model Filename (3rd set)",
    "MO3T": "Model Texture Hashes (3rd)",
    "MO3S": "Model Alt Textures (3rd)",
    "MOD4": "Female 1st Person Model",
    "MO4T": "Female 1st Person Texture Hashes",
    "MO4S": "Female 1st Person Alt Textures",
    "MOD5": "Model Filename (5th set)",
    "MO5T": "Model Texture Hashes (5th)",
    "MO5S": "Model Alt Textures (5th)",
    "MODB": "Model Bound Radius",
    "ICON": "Large Icon Filename",
    "MICO": "Small Icon Filename",
    "ICO2": "Female Large Icon Filename",
    "MIC2": "Female Small Icon Filename",

    # ── Object Bounds ──
    "OBND": "Object Bounds",

    # ── Keywords ──
    "KWDA": "Keyword FormIDs",
    "KSIZ": "Keyword Count",

    # ── Scripts (VMAD — Papyrus) ──
    "VMAD": "Virtual Machine Adapter (Scripts)",

    # ── TES4 Header ──
    "HEDR": "File Header Data",
    "CNAM": "Author",
    "SNAM": "Summary / Description",
    "MAST": "Master Plugin Filename",
    "ONAM": "Overridden Forms",
    "INTV": "Internal Version",
    "INCC": "Internal Cell Count",

    # ── Common item fields ──
    "ETYP": "Equipment Type",
    "BIDS": "Block Bash Impact Data Set",
    "BAMT": "Alternate Block Material",
    "YNAM": "Pick Up Sound",
    "ZNAM": "Put Down Sound",
    "EAMT": "Enchantment Amount / Charge",
    "EITM": "Object Effect (Enchantment)",
    "ANAM": "Attenuation / Keywords (context)",
    "TNAM": "Texture / Template / Text",
    "RNAM": "Race / Header / Prompt",
    "QNAM": "Quest / Header (context)",
    "WNAM": "First Person Model Object / Worn Armor",
    "INAM": "Impact Data Set / Idle",
    "VNAM": "Detection Sound Level / Voice Type",
    "NAM0": "Marker / Color (context)",
    "NAM1": "Dialog Response Text / Data",
    "NAM2": "Data",
    "NAM3": "Data",
    "NAM4": "Data",
    "NAM5": "Data",
    "NAM6": "Data / Marker",
    "NAM7": "Data / Marker",
    "NAM8": "Data / Marker",
    "NAM9": "Data / Marker",

    # ── Conditions ──
    "CTDA": "Condition Data",
    "CIS1": "Condition Variable Name 1",
    "CIS2": "Condition Variable Name 2",
    "CITC": "Condition Item Count",

    # ── NPC_ ──
    "ACBS": "NPC Configuration",
    "AIDT": "AI Data (Aggression, etc.)",
    "PKID": "AI Package FormID",
    "SPLO": "Actor Spell / Ability",
    "PRKR": "Perk (with Rank)",
    "PRKZ": "Perk (alternative)",
    "COCT": "Container Item Count",
    "CNTO": "Container Item Entry",
    "COED": "Extra Owner Data",
    "VTCK": "Voice Type",
    "TPLT": "Template NPC",
    "DOFT": "Default Outfit",
    "SOFT": "Sleep Outfit",
    "DPLT": "Default Package List",
    "CRIF": "Crime Faction",
    "FTST": "Face Textures Set",
    "QSTI": "Quest Item (Dialogue)",
    "SHRT": "Short Name",
    "ATKR": "Attack Race",
    "ATKD": "Attack Data",
    "ATKE": "Attack Event",
    "SPCT": "Spell Count",
    "TINI": "Tint Index",
    "TINC": "Tint Color",
    "TINV": "Tint Value",
    "TIAS": "Tint Preset",
    "NAM5": "NPC Unknown",
    "NAM6": "NPC Height",
    "NAM7": "NPC Weight",
    "NAM8": "NPC Sound / Template Data",
    "NAM9": "NPC Face Morph",
    "NAMA": "NPC Face Parts",
    "LNAM": "NPC Hair Color",
    "HCLF": "NPC Hair Color (FormID)",
    "ZNAM": "NPC Combat Style",
    "GNAM": "Gift Filter",
    "ECOR": "NPC Class",
    "DSTD": "Destruction Stage Data",
    "DSTF": "Destruction Stage End Flag",
    "DEST": "Destruction Header",
    "DMDL": "Destruction Stage Model",
    "DMDT": "Destruction Stage Model Textures",

    # ── Factions ──
    "XNAM": "Faction Relation",
    "MNAM": "Male Marker / Faction Data",
    "VEND": "Vendor List",
    "VENV": "Vendor Values",
    "JAIL": "Jail Outfit",
    "WAIT": "Wait Marker",
    "STOL": "Stolen Goods Container",
    "PLCN": "Player Crime Container",
    "CRGR": "Crime Group",

    # ── ARMO / ARMA ──
    "BODT": "Body Template (Oldrim compat)",
    "BOD2": "Body Template (SSE)",
    "MODL": "Model Path",
    "RNAM": "Race (Armor Addon)",
    "SNDD": "Sound Descriptor",
    "BMCT": "Ragdoll Constraint Template",

    # ── WEAP ──
    "CRDT": "Critical Data",
    "BNAM": "Weapon Template / Sheath Node",
    "CNAM": "Template (WEAP context)",
    "ENAM": "Enchantment / Effect",
    "NNAM": "Embedded Weapon Node",
    "SNAM": "Sound (Attack / Equip)",

    # ── BOOK ──
    "ITXT": "Book Text (localized)",

    # ── ALCH (Potions/Poisons/Food) ──
    "EFID": "Base Effect (Magic Effect FormID)",
    "EFIT": "Effect Item (Magnitude/Area/Duration)",
    "SPIT": "Spell / Potion Data (type, cost, flags)",

    # ── SPEL / ENCH / SCRL / INGR ──
    "OBTE": "Object Template Data",
    "OBTF": "Object Template Flags",
    "OBTS": "Object Template Subrecord",

    # ── MGEF (Magic Effect) ──
    "SNDD": "Sound Data (Magic Effect)",
    "MDOB": "Menu Display Object",
    "DNAM": "Magic Effect Data",

    # ── PERK ──
    "PRKE": "Perk Effect Header",
    "PRKF": "Perk Effect End Marker",
    "EPFT": "Entry Point Function Type",
    "EPFD": "Entry Point Function Data",
    "EPF2": "Entry Point Button Label",
    "EPF3": "Entry Point Script Fragment",
    "EPFB": "Entry Point Function Base",

    # ── QUST ──
    "ANAM": "Quest Next Alias ID",
    "DNAM": "Quest Flags / Data",
    "FLTR": "Quest Object Window Filter",
    "NEXT": "Quest Marker",
    "INDX": "Quest Objective / Log Entry Index",
    "QSDT": "Quest Stage Flags",
    "QOBJ": "Quest Objective Data",
    "NNAM": "Quest Objective Display Text",
    "SCHR": "Script Header",
    "SCDA": "Script Compiled Data",
    "SCTX": "Script Source",
    "QSTA": "Quest Alias",
    "ALST": "Alias Reference Start",
    "ALLS": "Alias Location Start",
    "ALID": "Alias Name",
    "ALDN": "Alias Display Name",
    "ALFR": "Alias Forced Reference",
    "ALFL": "Alias Forced Location",
    "ALFE": "Alias External Alias Reference",
    "ALFI": "Alias Find Matching Ref Info",
    "ALFA": "Alias Find Matching Ref (From Event)",
    "ALEA": "Alias External Alias (Event-based)",
    "ALEQ": "Alias External Alias (Quest)",
    "ALED": "Alias End",
    "ALCO": "Alias Create Reference Container",
    "ALCL": "Alias Create Reference Level",
    "ALDN": "Alias Display Name",
    "ALUA": "Alias Unique Actor",
    "ALCA": "Alias Create Reference Alias",

    # ── CELL ──
    "XCLC": "Cell Grid",
    "XCLL": "Cell Lighting",
    "XCLW": "Cell Water Height",
    "XCLR": "Cell Regions",
    "XCIM": "Cell Image Space",
    "XCET": "Cell Unknown (SSE)",
    "XEZN": "Cell Encounter Zone",
    "XCMO": "Cell Music Type",
    "XCAS": "Cell Acoustic Space",
    "XILL": "Cell Unknown",
    "XCWT": "Cell Water Type",
    "XOWN": "Cell Owner",
    "XRNK": "Cell Owner Faction Rank",
    "XNAM": "Cell Attach Ref",
    "LTMP": "Cell Lighting Template",
    "LNAM": "Cell Lighting Template Flags",
    "XCCM": "Cell Sky/Weather From Region",
    "XWEM": "Cell Water Environment Map",
    "TVDT": "Cell Occlusion Data",
    "MHDT": "Cell Max Height Data",

    # ── REFR / ACHR (Placed objects & NPCs) ──
    "NAME": "Base FormID (Reference)",
    "XSCL": "Reference Scale",
    "XTEL": "Teleport Destination",
    "XLOC": "Lock Data",
    "XESP": "Enable Parent",
    "XEMI": "Emittance",
    "XLCM": "Level Modifier",
    "XPRD": "Patrol Data (idle time)",
    "XPPA": "Patrol Marker",
    "XMRK": "Map Marker",
    "XLKR": "Linked Reference",
    "XLRT": "Linked Ref Transient",
    "XRDS": "Radius",
    "XAPD": "Activate Parents Flags",
    "XAPR": "Activate Parent Ref",
    "XLIB": "Leveled Item Base",
    "XLRL": "Location Reference",
    "XNDP": "Navigation Door Link",
    "XPRM": "Primitive",
    "XRMR": "Ref Room Marker",
    "XRGD": "Ragdoll Data",
    "XRGB": "Ragdoll Biped Data",
    "XMBR": "Multibound Reference",
    "XPWR": "Power Links",
    "XCNT": "Item Count (Placed)",
    "XOWN": "Ownership",
    "XRNK": "Owner Faction Rank",
    "XHOR": "Horse",
    "XHTW": "Head Tracking Weight",
    "XFVC": "Favor Cost",
    "XLOD": "LOD Data",
    "XWCU": "Water Current Velocity",
    "XACT": "Action Flag",
    "XPCI": "Paint (prev. link info)",
    "ONAM": "Open by Default / Overrides",
    "XMBO": "Multibound Data",
    "XMBP": "Multibound Primitive Data",
    "XILS": "Interior Lighting Sector",

    # ── WRLD ──
    "WCTR": "World Center Cell",
    "WNAM": "Parent Worldspace",
    "PNAM": "Parent World Use Flags",
    "MNAM": "World Map Data",
    "ONAM": "World Map Offset Data",
    "UNAM": "World Unknown",
    "XXXX": "Oversize Data Length",
    "OFST": "Offset Data (obsolete)",
    "ZNAM": "Music",
    "XLCN": "Location",
    "TNAM": "HD LOD Diffuse Texture",
    "UNAM": "HD LOD Normal Texture",
    "XWEM": "Water Environment Map",

    # ── DIAL ──
    "QSTI": "Quest / Info",
    "BNAM": "Branch (Dialog)",
    "SNAM": "Subtype",
    "TIFC": "Info Count",

    # ── INFO ──
    "TRDT": "Response Data",
    "NAM1": "Response Text",
    "NAM2": "Script Notes",
    "NAM3": "Edits",
    "TCLT": "Choice Link (INFO)",
    "TCLF": "Choice Link 2 (INFO)",
    "TWAT": "Wait (INFO)",
    "ENAM": "Response Flags",
    "LNAM": "Shared Info",
    "RNAM": "Response Number",

    # ── PACK (AI Package) ──
    "ANAM": "Package Idle Flags / Flags",
    "BNAM": "Package Template",
    "CNAM": "Package Combat Style",
    "PKCU": "Package Use Count",
    "PKDT": "Package Schedule / General Data",
    "PSDT": "Package Schedule Data",
    "PLDT": "Package Location Data",
    "PTDA": "Package Target Data",
    "TDAT": "Package Target Data (alt)",
    "PDTO": "Package Topic / Data Link",
    "POBA": "Package On Begin Idle Anim",
    "POEA": "Package On End Idle Anim",
    "POCA": "Package On Change Idle Anim",
    "UNAM": "Package Use Flags",
    "XNAM": "Package Marker",
    "PKC2": "Package Use Count 2",

    # ── IDLE ──
    "ENAM": "Animation Event",

    # ── RACE ──
    "WNAM": "Skin (ARMO form)",
    "GNAM": "Body Data",
    "NAM1": "Facegen - Main Clamp",
    "NAM2": "Facegen - Face Clamp",
    "MTNM": "Movement Type Names",
    "ATKD": "Attack Data",
    "ATKE": "Attack Event",
    "SNAM": "Unknown Sound",
    "HCLF": "Default Hair Color",
    "TINL": "Tint Index (Last)",
    "PHTN": "Phoneme Target Names",
    "PHWT": "Phoneme Target Weights",
    "MPAI": "Face Morph Presets (Indices)",
    "MPAV": "Face Morph Presets (Values)",
    "DFTF": "Default Face Texture (Female)",
    "DFTM": "Default Face Texture (Male)",
    "FTSF": "Face Texture Set (Female)",
    "FTSM": "Face Texture Set (Male)",

    # ── LSCR (Load Screen) ──
    "NNAM": "Loading Screen Text",
    "SNAM": "Initial Scale",
    "ONAM": "Rotation",
    "XNAM": "Rotation Offset",
    "MOD2": "Camera Path Model",

    # ── MESG ──
    "ITXT": "Button Text",
    "INAM": "Icon (Message)",
    "TNAM": "Title (Message, overloaded)",

    # ── FLST ──
    "LNAM": "FormID List Entry",

    # ── SCEN (Scene) ──
    "HTID": "Head Track Actor ID",
    "HNAM": "Scene Phase Start",
    "SNAM": "Scene Start / Sound",
    "ENAM": "Scene End",
    "WNAM": "Scene Weather / Editor Width",
    "PNAM": "Scene Phase End / Previous",
    "INAM": "Scene Index",
    "VNAM": "Scene Verb (Action)",

    # ── LCTN (Location) ──
    "LCPR": "Location Ref (Actor)",
    "LCSR": "Location Ref (Static)",
    "LCUN": "Location Ref (Unknown)",
    "LCEC": "Location Ref (Encounter Cell)",
    "LCEP": "Location Ref (Enable Point)",
    "LCID": "Location Ref ID",

    # ── ECZN (Encounter Zone) ──
    "ENAM": "Encounter Zone Data",

    # ── COBJ (Constructible Object / Recipe) ──
    "BNAM": "Crafting Station Keyword",
    "CNAM": "Created Object FormID",
    "NAM1": "Created Object Count",

    # ── LVLI / LVLN / LVSP (Leveled Lists) ──
    "LVLD": "Chance None",
    "LVLF": "Leveled List Flags",
    "LVLG": "Use Global (for chance)",
    "LLCT": "Leveled List Count",
    "LVLO": "Leveled List Entry",

    # ── WTHR ──
    "LNAM": "Lighting / Sun Damage",
    "NAM0": "Weather Colors (Sunrise)",
    "DALC": "Directional Ambient Light Colors",
    "MODL": "Aurora Model",

    # ── WATR ──
    "ANAM": "Water Opacity",
    "FNAM": "Water Flags",
    "MNAM": "Water Material",
    "BNAM": "Water Unknown",
    "INAM": "Water Image Space",

    # ── SNDR (Sound Descriptor) ──
    "CNAM": "Sound Category",
    "GNAM": "Sound Output Model",
    "SNAM": "Sound Files",
    "BNAM": "Sound Frequency Shift",
    "ANAM": "Sound Attenuation Values",
    "ONAM": "Sound Output Model (Static)",
    "LNAM": "Sound Looping Data",
    "FNAM": "Sound Flags/Conditions",

    # ── SHOU / WOOP ──
    "SNAM": "Shout Words of Power",
    "TNAM": "Translation (Word of Power)",

    # ── Explosion / Projectile / Hazard ──
    "MNAM": "Projectile Muzzle Flash Model",
    "NAM1": "Explosion Muzzle Flash Duration",
    "NAM2": "Hazard Data",

    # ── Generic ──
    "XXXX": "Oversize Subrecord Data Length",
    "OFST": "Offset Data (Deprecated)",
    "DELE": "Deleted Record Marker",
}


# ─────────────────────────────────────────────────────────
# 4. RECORD HEADER FLAGS
# ─────────────────────────────────────────────────────────
class RecordFlag(IntFlag):
    """Флаги заголовка записи (record header flags, 4 bytes)."""
    NONE                    = 0x00000000
    ESM                     = 0x00000001  # Мастер-файл
    LOCALIZED               = 0x00000080  # Строки через STRINGS/ILSTRINGS/DLSTRINGS
    LIGHT_MASTER            = 0x00000200  # ESL — лёгкий мастер (SSE/FO4)
    COMPRESSED              = 0x00040000  # Данные сжаты zlib
    CANT_WAIT               = 0x00080000  # Нельзя ждать в этой ячейке

    # Общие для разных типов записей:
    DELETED                 = 0x00000020  # Помечена как удалённая
    CONSTANT                = 0x00000040  # Constant / Hidden from local map
    INITIALLY_DISABLED      = 0x00000800  # Начально выключена
    IGNORED                 = 0x00001000  # Игнорируется
    VISIBLE_WHEN_DISTANT    = 0x00008000  # Видна на дальних дистанциях
    DANGEROUS               = 0x00020000  # Random anim start / Dangerous
    NO_AI_ACQUIRE           = 0x02000000  # NPC не подбирает
    NAVMESH_FILTER          = 0x04000000  # NavMesh — генерирует фильтрующую геометрию
    NAVMESH_BOUNDING_BOX    = 0x08000000  # NavMesh — bounding box
    REFLECTED_BY_AUTO_WATER = 0x10000000  # Reflected / Non-Pipboy / Obstacle
    NAVMESH_GROUND          = 0x40000000  # NavMesh — ground
    MULTIBOUND              = 0x20000000  # Child can use / Multibound


# ─────────────────────────────────────────────────────────
# 5. GROUP TYPES
# ─────────────────────────────────────────────────────────
class GroupType(IntEnum):
    """Типы GRUP-заголовков."""
    TOP                       = 0  # Верхнеуровневая группа (по сигнатуре записи)
    WORLD_CHILDREN            = 1  # Дочерние записи мира
    INTERIOR_CELL_BLOCK       = 2  # Блок внутренних ячеек
    INTERIOR_CELL_SUBBLOCK    = 3  # Подблок внутренних ячеек
    EXTERIOR_CELL_BLOCK       = 4  # Блок внешних ячеек
    EXTERIOR_CELL_SUBBLOCK    = 5  # Подблок внешних ячеек
    CELL_CHILDREN             = 6  # Дочерние записи ячейки
    TOPIC_CHILDREN            = 7  # Дочерние записи топика диалога
    CELL_PERSISTENT_CHILDREN  = 8  # Persistent children ячейки
    CELL_TEMPORARY_CHILDREN   = 9  # Temporary children ячейки
    CELL_VISIBLE_DISTANT      = 10 # Visible distant children ячейки


# ─────────────────────────────────────────────────────────
# 6. NPC FLAGS  (ACBS subrecord)
# ─────────────────────────────────────────────────────────
class NPCFlag(IntFlag):
    """NPC_/ACBS — основные флаги NPC (первые 4 байта ACBS)."""
    NONE                = 0x00000000
    FEMALE              = 0x00000001
    ESSENTIAL           = 0x00000002
    IS_CHARGEN_FACE_PRESET = 0x00000004
    RESPAWN             = 0x00000008
    AUTO_CALC_STATS     = 0x00000010
    UNIQUE              = 0x00000020
    DOESNT_AFFECT_STEALTH = 0x00000040
    PC_LEVEL_MULT       = 0x00000080
    # uses template flags:
    USE_TEMPLATE_0      = 0x00000100  # (not commonly named)
    PROTECTED           = 0x00000800
    SUMMONABLE          = 0x00004000
    DOESNT_BLEED        = 0x00010000
    OWNED               = 0x00040000  # Bleedout Override
    OPPOSITE_GENDER_ANIMS = 0x00080000
    SIMPLE_ACTOR        = 0x00100000
    LOOPED_SCRIPT       = 0x00200000  # Doesn't apply in SSE normally
    LOOPED_AUDIO        = 0x10000000
    IS_GHOST             = 0x20000000
    INVULNERABLE        = 0x80000000


class NPCTemplateFlag(IntFlag):
    """NPC_/ACBS — какие данные брать из шаблона (Template Flags, 2 bytes)."""
    NONE              = 0x0000
    USE_TRAITS        = 0x0001
    USE_STATS         = 0x0002
    USE_FACTIONS      = 0x0004
    USE_SPELL_LIST    = 0x0008
    USE_AI_DATA       = 0x0010
    USE_AI_PACKAGES   = 0x0020
    USE_MODEL_ANIM    = 0x0040  # unused in SSE
    USE_BASE_DATA     = 0x0080
    USE_INVENTORY     = 0x0100
    USE_SCRIPT        = 0x0200
    USE_DEF_PACK_LIST = 0x0400
    USE_ATTACK_DATA   = 0x0800
    USE_KEYWORDS      = 0x1000


# ─────────────────────────────────────────────────────────
# 7. WEAPON TYPES / ANIMATION TYPES
# ─────────────────────────────────────────────────────────
class WeaponAnimationType(IntEnum):
    """WEAP/DNAM — Animation Type (byte)."""
    HAND_TO_HAND  = 0
    MELEE_1H_SWORD = 1
    MELEE_1H_DAGGER = 2
    MELEE_1H_AXE = 3
    MELEE_1H_MACE = 4
    MELEE_2H_SWORD = 5
    MELEE_2H_AXE = 6   # aka Battleaxe/Warhammer
    BOW           = 7
    STAFF         = 8
    CROSSBOW      = 9
    MELEE_1H_RAPIER = 10   # not used in vanilla
    MELEE_1H_KATANA = 11   # not used in vanilla


class WeaponFlag(IntFlag):
    """WEAP/DNAM — Weapon Flags."""
    NONE                = 0x0000
    IGNORES_NORMAL_RESISTANCE = 0x0001
    AUTOMATIC           = 0x0002
    HAS_SCOPE           = 0x0004
    CANT_DROP            = 0x0008
    HIDE_BACKPACK       = 0x0010
    EMBEDDED_WEAPON     = 0x0020
    DONT_USE_1ST_PERSON_IS_ANIM = 0x0040
    NON_PLAYABLE        = 0x0080
    MINOR_CRIME         = 0x0001  # alternate context
    RANGE_FIXED         = 0x0002  # alternate context
    NOT_USED_IN_NORMAL_COMBAT = 0x0004  # alternate context
    BOUND_WEAPON        = 0x2000
    NPC_ONLY            = 0x00002000  # from flag2 (second set)


# ─────────────────────────────────────────────────────────
# 8. ARMOR / BOD2 FLAGS (Biped Object)
# ─────────────────────────────────────────────────────────
class BipedObjectFlag(IntFlag):
    """BOD2 / BODT — First Person Body Part Flags (slots 30-61)."""
    NONE              = 0x00000000
    SLOT_30_HEAD      = 0x00000001
    SLOT_31_HAIR      = 0x00000002
    SLOT_32_BODY      = 0x00000004
    SLOT_33_HANDS     = 0x00000008
    SLOT_34_FOREARMS  = 0x00000010
    SLOT_35_AMULET    = 0x00000020
    SLOT_36_RING      = 0x00000040
    SLOT_37_FEET      = 0x00000080
    SLOT_38_CALVES    = 0x00000100
    SLOT_39_SHIELD    = 0x00000200
    SLOT_40_TAIL      = 0x00000400
    SLOT_41_LONGHAIR  = 0x00000800
    SLOT_42_CIRCLET   = 0x00001000
    SLOT_43_EARS      = 0x00002000
    SLOT_44           = 0x00004000
    SLOT_45           = 0x00008000
    SLOT_46           = 0x00010000
    SLOT_47           = 0x00020000
    SLOT_48           = 0x00040000
    SLOT_49_MOD_MOUTH = 0x00080000
    SLOT_50_MOD_NECK  = 0x00100000
    SLOT_51_MOD_CHEST = 0x00200000
    SLOT_52_MOD_BACK  = 0x00400000
    SLOT_53           = 0x00800000
    SLOT_54           = 0x01000000
    SLOT_55           = 0x02000000
    SLOT_56           = 0x04000000
    SLOT_57           = 0x08000000
    SLOT_58           = 0x10000000
    SLOT_59           = 0x20000000
    SLOT_60_FX01      = 0x40000000
    SLOT_61           = 0x80000000


class ArmorType(IntEnum):
    """BOD2 — Armor Type (4 bytes, offset 4 in BOD2)."""
    LIGHT_ARMOR = 0
    HEAVY_ARMOR = 1
    CLOTHING    = 2


# ─────────────────────────────────────────────────────────
# 9. MAGIC EFFECT — Archetype, Casting Type, Delivery
# ─────────────────────────────────────────────────────────
class MagicEffectArchetype(IntEnum):
    """MGEF/DATA — Effect Archetype."""
    VALUE_MODIFIER         = 0
    SCRIPT                 = 1
    DISPEL                 = 2
    CURE_DISEASE           = 3
    ABSORB                 = 4
    DUAL_VALUE_MODIFIER    = 5
    CALM                   = 6
    DEMORALIZE             = 7
    FRENZY                 = 8
    DISARM                 = 9
    COMMAND_SUMMONED       = 10
    INVISIBILITY           = 11
    LIGHT                  = 12
    DARKNESS               = 13  # not used in vanilla
    NIGHTEYE               = 14
    LOCK                   = 15
    OPEN                   = 16
    BOUND_WEAPON           = 17
    SUMMON_CREATURE        = 18
    DETECT_LIFE            = 19
    TELEKINESIS            = 20
    PARALYSIS              = 21
    REANIMATE              = 22
    SOUL_TRAP              = 23
    TURN_UNDEAD            = 24
    GUIDE                  = 25
    WEREWOLF_FEED          = 26
    CURE_PARALYSIS         = 27
    CURE_ADDICTION         = 28
    CURE_POISON            = 29
    CONCUSSION             = 30
    VALUE_AND_PARTS        = 31
    ACCUMULATE_MAGNITUDE   = 32
    STAGGER                = 33
    PEAK_VALUE_MODIFIER    = 34
    CLOAK                  = 35
    WEREWOLF               = 36
    SLOW_TIME              = 37
    RALLY                  = 38
    ENCHANCE_WEAPON        = 39
    SPAWN_HAZARD           = 40
    ETHEREALIZE            = 41
    BANISH                 = 42
    SPAWN_SCRIPTED_REF     = 43  # SSE
    DISGUISE               = 44
    GRAB_ACTOR             = 45
    VAMPIRE_LORD           = 46


class CastingType(IntEnum):
    """MGEF/SPIT — Casting Type."""
    CONSTANT_EFFECT = 0
    FIRE_AND_FORGET = 1
    CONCENTRATION   = 2
    SCROLL          = 3  # (only for scroll items)


class DeliveryType(IntEnum):
    """MGEF/SPIT — Delivery / Targeting."""
    SELF           = 0
    CONTACT        = 1
    AIMED          = 2
    TARGET_ACTOR   = 3
    TARGET_LOCATION = 4


class SpellType(IntEnum):
    """SPIT — Spell Type (for SPEL records)."""
    SPELL       = 0
    DISEASE     = 1
    POWER       = 2
    LESSER_POWER = 3
    ABILITY     = 4
    POISON      = 5
    ENCHANTMENT = 6  # not normally in SPEL
    POTION      = 7  # not normally in SPEL
    WORM        = 8
    INGREDIENT  = 9  # for ALCH
    LEVELED_SPELL = 10
    ADDICTION   = 11
    VOICE       = 12
    STAFF_ENCHANT = 13
    SCROLL2     = 14


# ─────────────────────────────────────────────────────────
# 10. ACTOR VALUES (Skills & Attributes)
# ─────────────────────────────────────────────────────────
class ActorValue(IntEnum):
    """Actor Values — навыки и атрибуты Skyrim.
    Используются в MGEF, NPC_, AVIF, условиях и т.д."""
    AGGRESSION        = 0
    CONFIDENCE        = 1
    ENERGY            = 2
    MORALITY          = 3
    MOOD              = 4
    ASSISTANCE        = 5
    ONE_HANDED        = 6
    TWO_HANDED        = 7
    MARKSMAN          = 8   # Archery
    BLOCK             = 9
    SMITHING          = 10
    HEAVY_ARMOR       = 11
    LIGHT_ARMOR       = 12
    PICKPOCKET        = 13
    LOCKPICKING       = 14
    SNEAK             = 15
    ALCHEMY           = 16
    SPEECHCRAFT       = 17  # Speech
    ALTERATION        = 18
    CONJURATION       = 19
    DESTRUCTION       = 20
    ILLUSION          = 21
    RESTORATION       = 22
    ENCHANTING        = 23
    HEALTH            = 24
    MAGICKA           = 25
    STAMINA           = 26
    HEALRATE          = 27
    MAGICKARATE       = 28
    STAMINARATE       = 29
    SPEEDMULT         = 30
    INVENTORYWEIGHT   = 31
    CARRYWEIGHT       = 32
    CRITICALCHANCE    = 33
    MELEEDAMAGE       = 34
    UNARMEDDAMAGE     = 35
    MASS              = 36
    VOICEPOINTS       = 37
    VOICERATE         = 38
    DAMAGERESIST      = 39
    POISONRESIST      = 40
    RESISTFIRE        = 41
    RESISTSHOCK       = 42
    RESISTFROST       = 43
    RESISTMAGIC       = 44
    RESISTDISEASE     = 45
    # ... далее перечислены менее частые AV
    PARALYSIS         = 46
    INVISIBILITY      = 47
    NIGHTEYE          = 48
    DETECTLIFERANGE   = 49
    WATERBREATHING    = 50
    WATERWALKING      = 51
    FAME              = 52  # unused
    INFAMY            = 53  # unused
    JUMPINGBONUS      = 54
    WARDPOWER         = 55
    RIGHTITEMCHARGE   = 56
    ARMORPERKS        = 57
    SHIELDPERKS       = 58
    WARDDEFLECTION    = 59
    VARIABLE01        = 60
    VARIABLE02        = 61
    VARIABLE03        = 62
    VARIABLE04        = 63
    VARIABLE05        = 64
    VARIABLE06        = 65
    VARIABLE07        = 66
    VARIABLE08        = 67
    VARIABLE09        = 68
    VARIABLE10        = 69
    BOWSPEEDBONUS     = 70
    FAVORACTIVE       = 71
    FAVORSPERDAY      = 72
    FAVORSPERDAYTIMER = 73
    LEFTITEMCHARGE    = 74
    ABSORBCHANCE      = 75
    BLINDNESS         = 76
    WEAPONSPEEDMULT   = 77
    SHOUTRECOVERYMULT = 78
    BOWSTAGGERBONUS   = 79
    TELEKINESIS       = 80
    FAVORPOINTSBONUS  = 81
    LASTBRIBEDINTIMIDATED = 82
    LASTFLATTERED     = 83
    MOVEMENTNOISEMULT = 84
    BYPASSVENDORSTOLENCHECK = 85
    BYPASSVENDORKEYWORDCHECK = 86
    WAITINGFORPLAYER  = 87
    ONEHANDEDMODIFIER = 88
    TWOHANDEDMODIFIER = 89
    MARKSMANMODIFIER  = 90
    BLOCKMODIFIER     = 91
    SMITHINGMODIFIER  = 92
    HEAVYARMORMODIFIER = 93
    LIGHTARMORMODIFIER = 94
    PICKPOCKETMODIFIER = 95
    LOCKPICKINGMODIFIER = 96
    SNEAKINGMODIFIER  = 97
    ALCHEMYMODIFIER   = 98
    SPEECHCRAFTMODIFIER = 99
    ALTERATIONMODIFIER = 100
    CONJURATIONMODIFIER = 101
    DESTRUCTIONMODIFIER = 102
    ILLUSIONMODIFIER  = 103
    RESTORATIONMODIFIER = 104
    ENCHANTINGMODIFIER = 105
    ONEHANDEDSKILLADVANCE = 106
    TWOHANDEDSKILLADVANCE = 107
    MARKSMANSKILLADVANCE = 108
    BLOCKSKILLADVANCE = 109
    SMITHINGSKILLADVANCE = 110
    HEAVYARMORSKILLADVANCE = 111
    LIGHTARMORSKILLADVANCE = 112
    PICKPOCKETSKILLADVANCE = 113
    LOCKPICKINGSKILLADVANCE = 114
    SNEAKINGSKILLADVANCE = 115
    ALCHEMYSKILLADVANCE = 116
    SPEECHCRAFTSKILLADVANCE = 117
    ALTERATIONSKILLADVANCE = 118
    CONJURATIONSKILLADVANCE = 119
    DESTRUCTIONSKILLADVANCE = 120
    ILLUSIONSKILLADVANCE = 121
    RESTORATIONSKILLADVANCE = 122
    ENCHANTINGSKILLADVANCE = 123
    LEFTWEAPONSPEEDMULT = 124
    DRAGONSOULS       = 125
    COMBATHEALTHREGEN = 126
    ONEHANDEDPOWERMOD = 127
    TWOHANDEDPOWERMOD = 128
    MARKSMANPOWERMOD  = 129
    BLOCKPOWERMOD     = 130
    SMITHINGPOWERMOD  = 131
    HEAVYARMORPOWERMOD = 132
    LIGHTARMORPOWERMOD = 133
    PICKPOCKETPOWERMOD = 134
    LOCKPICKINGPOWERMOD = 135
    SNEAKINGPOWERMOD  = 136
    ALCHEMYPOWERMOD   = 137
    SPEECHCRAFTPOWERMOD = 138
    ALTERATIONPOWERMOD = 139
    CONJURATIONPOWERMOD = 140
    DESTRUCTIONPOWERMOD = 141
    ILLUSIONPOWERMOD  = 142
    RESTORATIONPOWERMOD = 143
    ENCHANTINGPOWERMOD = 144
    DRAGONREND        = 145
    ATTACKDAMAGEMULT  = 146
    HEALRATEMULT      = 147  # Combat Health Regen Mult (SSE)
    MAGICKARATEMULT   = 148
    STAMINARATEMULT   = 149
    WEREWOLFPERKS     = 150
    VAMPIREPERKS      = 151
    GRABACTOROFFSET   = 152
    GRABBED           = 153
    DEPRECATED05      = 154
    REFLECTDAMAGE     = 155


# ─────────────────────────────────────────────────────────
# 11. CELL FLAGS
# ─────────────────────────────────────────────────────────
class CellFlag(IntFlag):
    """CELL/DATA — Cell Flags (uint16)."""
    NONE                  = 0x0000
    IS_INTERIOR_CELL      = 0x0001
    HAS_WATER             = 0x0002
    CANT_TRAVEL_FROM_HERE = 0x0004  # Can't Fast Travel (previously INVERT_FAST_TRAVEL)
    NO_LOD_WATER          = 0x0008
    # 0x0010 unused
    PUBLIC_AREA           = 0x0020
    HAND_CHANGED          = 0x0040
    SHOW_SKY              = 0x0080
    USE_SKY_LIGHTING      = 0x0100


# ─────────────────────────────────────────────────────────
# 12. CONDITION FUNCTION INDEX → NAME  (наиболее частые)
# ─────────────────────────────────────────────────────────
CONDITION_FUNCTION_NAMES: Dict[int, str] = {
    0:   "GetWantBlocking",
    1:   "GetDistance",
    5:   "GetLocked",
    6:   "GetPos",
    8:   "GetAngle",
    10:  "GetStartingPos",
    11:  "GetStartingAngle",
    12:  "GetSecondsPassed",
    14:  "GetActorValue",
    18:  "GetCurrentTime",
    24:  "GetScale",
    25:  "IsMoving",
    26:  "IsTurning",
    27:  "GetLineOfSight",
    32:  "GetInSameCell",
    35:  "GetDisabled",
    36:  "MenuMode",
    39:  "GetDisease",
    41:  "GetClothingValue",
    42:  "SameFaction",
    43:  "SameRace",
    44:  "SameSex",
    45:  "GetDetected",
    46:  "GetDead",
    47:  "GetItemCount",
    48:  "GetGold",
    49:  "GetSleeping",
    50:  "GetTalkedToPC",
    53:  "GetScriptVariable",
    56:  "GetQuestRunning",
    58:  "GetStage",
    59:  "GetStageDone",
    60:  "GetFactionRankDifference",
    61:  "GetAlarmed",
    62:  "IsRaining",
    63:  "GetAttacked",
    64:  "GetIsCreature",
    65:  "GetLockLevel",
    66:  "GetShouldAttack",
    67:  "GetInCell",
    68:  "GetIsClass",
    69:  "GetIsRace",
    70:  "GetIsSex",
    71:  "GetInFaction",
    72:  "GetIsID",
    73:  "GetFactionRank",
    74:  "GetGlobalValue",
    75:  "IsSnowing",
    77:  "GetRandomPercent",
    79:  "GetQuestVariable",
    80:  "GetLevel",
    81:  "IsRotating",
    84:  "GetDeadCount",
    91:  "GetIsAlerted",
    98:  "GetPlayerControlsDisabled",
    99:  "GetHeadingAngle",
    101: "IsWeaponMagicOut",  # IsTorchOut
    102: "IsWeaponOut",       # IsShieldOut
    106: "IsFacingUp",
    107: "GetKnockedState",
    108: "GetWeaponAnimType",
    109: "IsWeaponSkillType",
    110: "GetCurrentAIPackage",
    111: "IsWaiting",
    112: "IsIdlePlaying",
    116: "IsIntimidatedbyPlayer",
    117: "IsPlayerInRegion",
    118: "GetActorAggroRadiusViolated",
    122: "GetCrime",
    123: "IsGreetingPlayer",
    125: "IsGuard",
    127: "HasBeenEaten",
    128: "GetStaminaPercentage",  # GetFatiguePercentage
    129: "HasBeenRead",
    130: "GetCommunityHealing",  # deprecated
    131: "GetMapMarkerVisible",  # deprecated
    136: "GetInWorldspace",
    141: "GetPCMiscStat",
    142: "GetPCFactionAttack",  # deprecated
    143: "GetCombatState",
    144: "GetWithinPackageLocation",
    149: "IsPlayersLastRiddenHorse",  # deprecated
    152: "GetGameDayOfWeek",  # deprecated
    161: "GetActorsInHigh",  # deprecated
    162: "HasLoaded3D",
    170: "IsTimePassing",
    172: "IsPleasant",
    173: "IsCloudy",
    175: "IsSmallBump",
    176: "GetBaseActorValue",
    177: "IsOwner",
    178: "IsCellOwner",
    180: "IsHorseStolen",
    181: "IsLeftUp",
    182: "IsSneaking",
    183: "IsRunning",
    184: "GetFriendHit",
    185: "IsInCombat",
    190: "IsInInterior",
    193: "IsWaterObject",  # deprecated
    195: "GetPlayerAction",
    196: "IsActorUsingATorch",
    197: "IsXBox",
    199: "GetInWorldspace",
    203: "GetPCIsClass",
    205: "GetPCIsRace",
    206: "GetPCIsSex",
    207: "GetPCInFaction",
    213: "GetIsPlayableRace",
    214: "GetOffersServicesNow",
    223: "IsWeaponOut",
    224: "HasSameEditorLocAsRef",
    225: "HasSameEditorLocAsRefAlias",
    226: "GetNoRumors",  # deprecated
    227: "GetCombatState",
    228: "GetWithinPackageLocation",
    230: "IsRidingMount",
    231: "IsFleeing",
    233: "IsInDangerousWater",
    237: "GetIgnoreFriendlyHits",
    242: "IsPlayersLastRiddenMount",
    244: "IsActor",
    246: "IsEssential",
    247: "IsPlayerMovingIntoNewSpace",
    248: "GetInCurrentLoc",
    249: "GetInCurrentLocAlias",
    250: "GetTimeDead",
    254: "HasLinkedRef",
    256: "IsChild",
    258: "GetStolenItemValueNoCrime",
    259: "GetLastPlayerAction",
    261: "IsPlayerActionActive",
    264: "IsTalkingActivatorActor",
    265: "IsInList",
    266: "GetStolenItemValue",
    267: "GetCrimeGoldViolent",
    268: "GetCrimeGoldNonviolent",
    272: "HasShout",
    274: "GetHasNote",
    280: "GetObjectiveFailed",
    282: "GetHitLocation",
    285: "IsPC1stPerson",
    286: "GetCauseofDeath",  # deprecated
    287: "IsLimbGone",
    288: "IsWeaponInList",
    291: "IsBribedbyPlayer",
    292: "GetRelationshipRank",
    293: "GetGroupMemberCount",  # deprecated
    294: "GetGroupTargetCount",  # deprecated
    298: "GetVATSValue",
    305: "GetIsVoiceType",
    306: "GetPlantedExplosive",  # deprecated
    309: "IsScenePackageRunning",
    310: "GetHealthPercentage",
    312: "GetIsObjectType",
    313: "PlayerVisualDetection",  # deprecated
    314: "PlayerAudioDetection",  # deprecated
    325: "GetIsCreatureType",
    327: "HasKey",
    329: "IsFurnitureEntryType",
    332: "GetInCurrentLocFormList",
    338: "GetInZone",
    339: "GetVelocity",
    340: "GetGraphVariableFloat",
    341: "HasPerk",
    342: "GetFactionRelation",
    343: "IsLastIdlePlayed",
    344: "GetPlayerTeammate",
    345: "GetPlayerTeammateCount",
    347: "GetActorCrimePlayerEnemy",
    348: "GetCrimeGold",
    349: "IsPlayerGrabbedRef",
    351: "GetKeywordItemCount",
    353: "GetDestructionStage",
    359: "GetIsAlignment",
    360: "IsProtected",
    362: "GetThreatRatio",
    365: "IsEnteringInteractionQuick",  # deprecated
    366: "IsCasting",
    367: "GetFlyingState",
    368: "IsInFavorState",
    369: "HasTwoHandedWeaponEquipped",
    370: "IsExitingInstant",  # deprecated
    372: "IsInFriendStatewithPlayer",
    373: "GetWithinDistance",
    375: "GetActorValuePercent",
    376: "IsUnique",
    378: "GetLastBumpDirection",
    381: "GetInfoChallangeSuccess",  # deprecated
    382: "GetIsInjured",  # deprecated
    383: "GetIsCrashLandRequest",
    384: "GetIsHastyLandRequest",
    385: "IsLinkedTo",
    387: "GetKeywordDataForCurrentLocation",  # deprecated
    391: "GetInSharedCrimeFactionList",
    392: "GetBribeSuccess",  # deprecated
    393: "GetIntimidateSuccess",  # deprecated
    394: "GetArrestedState",  # deprecated
    396: "GetArrestingActor",  # deprecated
    397: "EPTemperingItemIsEnchanted",
    398: "EPTemperingItemHasKeyword",
    402: "GetReplacedItemType",  # deprecated
    403: "IsAttacking",
    404: "IsPowerAttacking",
    405: "IsLastHostileActor",
    407: "GetGraphVariableInt",
    408: "GetCurrentShoutVariation",
    410: "ShouldAttackKill",
    414: "GetActivatorHeight",  # deprecated
    418: "EPMagic_IsAdvanceSkill",  # deprecated
    419: "WornHasKeyword",
    420: "GetPathingTarget",  # deprecated
    421: "GetPathingOwner",  # deprecated
    422: "HasMagicEffectKeyword",
    425: "IsNullPackageData",  # deprecated
    426: "GetNumericPackageData",
    427: "IsFurnitureAnimType",
    428: "IsFurnitureEntryType",
    429: "GetHighestRelationshipRank",
    430: "GetLowestRelationshipRank",
    431: "HasAssociationTypeAny",
    432: "HasFamilyRelationshipAny",
    434: "GetPathingCurrentSpeed",  # deprecated
    435: "GetPathingCurrentSpeedAngle",  # deprecated
    437: "EPAlchemyGetMakingPoison",
    438: "GetQuestCompleted",
    445: "IsGoreDisabled",  # deprecated
    446: "IsSceneActionComplete",  # deprecated
    448: "GetSpellUsageNum",  # deprecated
    449: "GetActorsInHigh",  # deprecated
    450: "HasLoaded3D",
    453: "HasKeyword",
    458: "GetNoBleedoutRecovery",  # deprecated
    461: "GetRelativeAngle",  # deprecated
    462: "GetMovementDirection",  # deprecated
    464: "IsBlocking",
    465: "HasEquippedSpell",
    467: "GetCurrentCastingType",
    468: "GetCurrentDeliveryType",
    469: "GetAttackState",  # deprecated
    470: "GetEventData",
    473: "GetIsGhost",
    477: "GetUnconscious",  # deprecated
    479: "GetRestrained",  # deprecated
    480: "IsInDialogueWithPlayer",
    487: "GetIsCurrentPackage",
    488: "IsCurrentFurnitureObj",
    489: "IsCurrentFurnitureRef",
    491: "GetDayOfWeek",  # deprecated
    493: "GetTalkedToPCParam",
    494: "IsPCSleeping",
    495: "IsPCAMurderer",
    497: "HasVampireFed",
    501: "GetPCExpelled",
    503: "GetPCFactionMurder",
    508: "GetPCEnemyofFaction",  # deprecated
    512: "GetPCFactionAttack",  # deprecated
    513: "GetDestroyed",  # deprecated
    515: "HasMagicEffect",
    516: "GetDefaultOpen",
    518: "GetAnimAction",  # deprecated
    519: "IsSpellTarget",
    520: "GetVATSMode",  # deprecated
    522: "GetPersuasionNumber",  # deprecated
    523: "GetVampireFeed",
    524: "GetCannibal",  # deprecated
    525: "GetIsClassDefault",  # deprecated
    528: "GetClassDefaultMatch",  # deprecated
    530: "GetInCellParam",
    531: "GetVatsTargetHeight",  # deprecated
    533: "GetIsGhost",
    534: "GetUnconscious",  # deprecated
    535: "GetRestrained",  # deprecated
    543: "GetIsUsedItem",  # deprecated
    544: "GetIsUsedItemType",  # deprecated
    545: "IsScenePlaying",
    547: "IsInDialogueWithPlayer",
    550: "GetLocationCleared",
    552: "GetIsPlayableRace",
    554: "GetOffersServicesNow",
    555: "HasAssociationType",
    556: "HasFamilyRelationship",
    558: "HasParentRelationship",
    559: "IsWarningAbout",
    560: "IsWeaponOut",
    561: "HasSpell",
    562: "IsTimePassing",
    563: "IsPleasant",
    564: "IsCloudy",
    565: "IsSmallBump",
    567: "GetBaseActorValue",
    568: "IsOwner",
    576: "GetVelocity",
    577: "GetGraphVariableFloat",
    579: "HasPerk",
    580: "GetFactionRelation",
    584: "IsLastIdlePlayed",
    589: "GetPlayerTeammate",
    590: "GetPlayerTeammateCount",
    597: "GetCrimeGold",
    600: "GetDestructionStage",
    602: "GetIsAlignment",
    606: "IsProtected",
    607: "GetThreatRatio",
    610: "IsCasting",
    611: "GetFlyingState",
    612: "IsInFavorState",
    613: "HasTwoHandedWeaponEquipped",
    614: "IsFurnitureExitType",  # deprecated
    615: "IsInFriendStatewithPlayer",
    617: "GetActorValuePercent",
    619: "IsUnique",
    621: "GetLastBumpDirection",
    625: "IsLinkedTo",
    629: "GetKeywordDataForCurrentLocation",  # deprecated
    631: "GetInSharedCrimeFactionList",
    633: "GetBribeSuccess",  # deprecated
    635: "GetIntimidateSuccess",  # deprecated
    637: "GetArrestedState",  # deprecated
    639: "GetArrestingActor",  # deprecated
    640: "IsAttacking",
    641: "IsPowerAttacking",
    642: "IsLastHostileActor",
    644: "GetGraphVariableInt",
    645: "GetCurrentShoutVariation",
    647: "ShouldAttackKill",
    650: "EPMagic_IsAdvanceSkill",  # deprecated
    651: "WornHasKeyword",
    653: "HasMagicEffectKeyword",
    654: "IsNullPackageData",  # deprecated
    655: "GetNumericPackageData",
    656: "IsFurnitureAnimType",
    657: "IsFurnitureEntryType",
    659: "GetHighestRelationshipRank",
    660: "GetLowestRelationshipRank",
    661: "HasAssociationTypeAny",
    662: "HasFamilyRelationshipAny",
    664: "EPAlchemyGetMakingPoison",
    675: "IsSceneActionComplete",
    677: "HasKeyword",
    678: "HasRefType",
    679: "LocationHasKeyword",
    680: "LocationHasRefType",
    681: "GetIsEditorLocation",  # deprecated
    682: "GetIsAliasRef",
    683: "GetIsEditorLocAlias",  # deprecated
    691: "IsSprinting",
    692: "IsBlocking",
    693: "HasEquippedSpell",
    694: "GetCurrentCastingType",
    695: "GetCurrentDeliveryType",
    696: "GetAttackState",
    697: "GetEventData",
    699: "IsCloserToAThanB",  # deprecated
    700: "LevelMinusPCLevel",  # deprecated
    704: "IsBleedingOut",
    706: "GetRelativeAngle",
    707: "GetMovementDirection",
    709: "IsInScene",
    713: "GetBribeSuccess",
    714: "GetIntimidateSuccess",
    715: "GetArrestedState",
    716: "GetArrestingActor",
    718: "HasVMScript",
    719: "GetVMScriptVariable",
    720: "GetVMQuestVariable",
    721: "IsMoving",
    722: "IsTurning",
    723: "GetWalkSpeed",
    724: "GetCurrentAIProcedure",
    725: "GetTrespassWarningLevel",
    726: "IsTrespassing",
    727: "IsInMyOwnedCell",
    728: "GetWindSpeed",
    729: "GetCurrentWeatherPercent",
    730: "GetIsCurrentWeather",
    731: "IsContinuingPackagePCNear",
    734: "GetHasBeenEaten",
    735: "GetSitting",
    738: "GetFurnitureMarkerEntryType",  # deprecated
    740: "GetTalkedToPC",
    741: "GetPCSleeping",
    742: "GetPCAMurderer",
    # ... SSE-specific:
    997: "WornApparelHasKeywordCount",
    # GetFormType / GetEquippedItemType  etc. used only rarely
}


# ─────────────────────────────────────────────────────────
# 13. CONDITION COMPARISON OPERATORS
# ─────────────────────────────────────────────────────────
class ConditionOperator(IntEnum):
    """Операторы сравнения в CTDA (верхние 3 бита байта type)."""
    EQUAL            = 0  # ==
    NOT_EQUAL        = 1  # !=
    GREATER_THAN     = 2  # >
    GREATER_OR_EQUAL = 3  # >=
    LESS_THAN        = 4  # <
    LESS_OR_EQUAL    = 5  # <=

CONDITION_OPERATOR_SYMBOLS: Dict[int, str] = {
    0: "==",
    1: "!=",
    2: ">",
    3: ">=",
    4: "<",
    5: "<=",
}


# ─────────────────────────────────────────────────────────
# 14. PERK ENTRY POINT TYPES
# ─────────────────────────────────────────────────────────
class PerkEntryPoint(IntEnum):
    """PRKE — Perk Entry Points (Skyrim SE)."""
    CALCULATE_WEAPON_DAMAGE          = 0
    CALCULATE_MY_CRITICAL_HIT_CHANCE = 1
    CALCULATE_MY_CRITICAL_HIT_DAMAGE = 2
    CALCULATE_WEAPON_ATTACK_AP_COST  = 3  # (unused in Skyrim)
    CALCULATE_MINE_EXPLODE_CHANCE    = 4  # (unused)
    ADJUST_LIMB_DAMAGE               = 5  # (unused)
    ADJUST_BOOK_SKILL_POINTS         = 6
    MODIFY_RECOVERED_HEALTH          = 7
    CALCULATE_SHOT_DISTANCE          = 8  # (unused)
    ADJUST_GAIN_SKILL_ROLL_CHANCE    = 9  # (unused)
    MODIFY_INCOMING_DAMAGE           = 10
    MODIFY_TARGET_DAMAGE_RESISTANCE  = 11
    MODIFY_SPELL_MAGNITUDE           = 12
    MODIFY_SPELL_DURATION            = 13
    MODIFY_SECONDARY_VALUE_WEIGHT    = 14
    MODIFY_ARMOR_WEIGHT              = 15
    MODIFY_INCOMING_STAGGER          = 16
    DODGE_ATTACK                     = 17
    RECOVER_ARROW                    = 18
    MODIFY_SPELL_COST                = 19
    MODIFY_PERCENT_BLOCKED           = 20
    MODIFY_SHIELD_DEFLECT_ARROW_CHANCE = 21
    MODIFY_INCOMING_SPELL_MAGNITUDE  = 22
    MODIFY_INCOMING_SPELL_DURATION   = 23
    MODIFY_PLAYER_INTIMIDATION       = 24
    MODIFY_PLAYER_REPUTATION         = 25
    MODIFY_FAVOR_POINTS              = 26
    MODIFY_BUYING_PRICES             = 27
    ADD_LEVELED_LIST_ON_DEATH        = 28
    GET_MAX_CARRY_WEIGHT             = 29
    MODIFY_ADDICTION_CHANCE           = 30  # (unused)
    MODIFY_ADDICTION_DURATION         = 31  # (unused)
    MODIFY_POSITIVE_CHEM_DURATION    = 32  # (unused)
    ACTIVATE                         = 33
    IGNORE_RUNNING_DURING_DETECTION  = 34
    IGNORE_BROKEN_LOCK               = 35
    MODIFY_ENEMY_CRITICAL_HIT_CHANCE = 36
    MODIFY_SNEAK_ATTACK_MULT         = 37
    MODIFY_MAX_PLACEABLE_MINES       = 38  # (unused)
    MODIFY_BOW_ZOOM                  = 39
    MODIFY_RECOVER_ARROW_CHANCE      = 40
    MODIFY_SKILL_USE                 = 41
    MODIFY_TELEKINESIS_DISTANCE      = 42
    MODIFY_TELEKINESIS_DAMAGE_MULT   = 43
    MODIFY_TELEKINESIS_DAMAGE        = 44
    MODIFY_BASHING_DAMAGE            = 45
    MODIFY_POWER_ATTACK_STAMINA      = 46
    MODIFY_POWER_ATTACK_DAMAGE       = 47
    MODIFY_SPELL_ABSORPTION          = 48
    MODIFY_ENCHANTMENT_POWER         = 49
    MODIFY_SOUL_GEM_ENCHANTING       = 50
    # SSE additional:
    MOD_TEMPERING_HEALTH             = 51
    MODIFY_ENCHANTMENT_CHARGE        = 52
    MODIFY_LOCKPICK_SWEET_SPOT       = 53
    MODIFY_SELL_PRICES               = 54
    CAN_PICKPOCKET_EQUIPPED_ITEM     = 55
    MODIFY_LOCKPICK_LEVEL_ALLOWED    = 56
    SET_LOCKPICK_STARTING_ARC        = 57
    SET_PROGRESSION_PICKING           = 58
    MAKE_LOCKPICKS_UNBREAKABLE       = 59
    MODIFY_ALCHEMY_EFFECTIVENESS     = 60
    APPLY_WEAPON_SWING_SPELL         = 61
    MODIFY_COMMANDED_ACTOR_LIMIT     = 62
    APPLY_SNEAKING_SPELL             = 63
    MODIFY_PLAYER_MAGIC_SLOWDOWN     = 64
    MODIFY_WARD_MAGNITUDE            = 65
    MODIFY_WARD_DURATION             = 66
    MODIFY_INITIAL_INGREDIENT_EFFECTS_LEARNED = 67
    PURIFY_ALCHEMY_INGREDIENTS       = 68
    FILTER_ACTIVATION                = 69
    CAN_DUAL_CAST_SPELL              = 70
    MODIFY_TEMPERING_ITEM            = 71
    MODIFY_ENCHANTING_POWER          = 72
    MODIFY_SOUL_PERK                 = 73  # deprecated name
    MODIFY_ALCHEMY_CRAFT             = 74
    SET_ACTIVATE_LABEL               = 75
    MODIFY_SHOUT                     = 76  # deprecated
    MODIFY_INCOMING_DAMAGE_MULT      = 77
    MODIFY_REFLECT_DAMAGE_CHANCE     = 78  # deprecated
    MODIFY_POISON_DOSE_COUNT         = 79
    SHOULD_APPLY_PLACED_ITEM         = 80
    MODIFY_ARMOR_RATING              = 81
    MODIFY_FALLING_DAMAGE            = 82
    MODIFY_LOCKPICK_CRIME_CHANCE     = 83
    MODIFY_INGREDIENTS_HARVESTED     = 84
    MODIFY_SPELL_RANGE               = 85  # Target
    MODIFY_POTIONS_CREATED           = 86
    MODIFY_LOCKPICK_KEY_BONUS        = 87  # (unused)
    MODIFY_DETECTION_LIGHT           = 88  # (unused)
    MODIFY_DETECTION_MOVEMENT        = 89  # (unused)


# ─────────────────────────────────────────────────────────
# 15. BOOK FLAGS (DATA subrecord in BOOK)
# ─────────────────────────────────────────────────────────
class BookFlag(IntFlag):
    """BOOK/DATA — Book Flags (byte 0 of DATA)."""
    NONE             = 0x00
    TEACHES_SKILL    = 0x01  # Teaches a skill
    CANT_BE_TAKEN    = 0x02  # Can't take
    TEACHES_SPELL    = 0x04  # Teaches a spell
    HAS_BEEN_READ    = 0x08  # not in file, runtime only
    # 0x10: advance actor value (SSE)


# ─────────────────────────────────────────────────────────
# 16. QUEST FLAGS
# ─────────────────────────────────────────────────────────
class QuestFlag(IntFlag):
    """QUST/DNAM — Quest Flags (uint16)."""
    NONE                      = 0x0000
    START_GAME_ENABLED        = 0x0001
    COMPLETED                 = 0x0002  # runtime
    ADD_IDLE_TOPIC_TO_HELLO   = 0x0004
    ALLOW_REPEATED_STAGES     = 0x0008
    STARTS_ENABLED            = 0x0010  # SSE (combined with START_GAME)
    DISPLAYED_IN_HUD          = 0x0020  # not commonly used
    FAILED                    = 0x0040  # runtime
    STAGE_WAIT                = 0x0080
    RUN_ONCE                  = 0x0100
    EXCLUDE_FROM_DIALOGUE_EXPORT = 0x0200
    WARN_ON_ALIAS_FILL_FAILURE = 0x0400


class QuestType(IntEnum):
    """QUST/DNAM — Quest Type."""
    NONE             = 0
    MAIN_QUEST       = 1
    MAGES_GUILD      = 2
    THIEVES_GUILD    = 3
    DARK_BROTHERHOOD = 4
    COMPANION_QUEST  = 5
    MISCELLANEOUS    = 6
    DAEDRIC          = 7
    SIDE_QUEST       = 8
    CIVIL_WAR        = 9
    DLC01_VAMPIRE    = 10  # Dawnguard
    DLC02_DRAGONBORN = 11  # Dragonborn


# ─────────────────────────────────────────────────────────
# 17. PACKAGE FLAGS (AI Package)
# ─────────────────────────────────────────────────────────
class PackageFlag(IntFlag):
    """PACK/PKDT — Package Flags (uint32)."""
    NONE                       = 0x00000000
    OFFERS_SERVICES            = 0x00000001
    MUST_COMPLETE              = 0x00000004
    MAINTAIN_SPEED_AT_GOAL     = 0x00000008
    UNLOCK_DOORS_AT_PACKAGE_START = 0x00000040
    UNLOCK_DOORS_AT_PACKAGE_END = 0x00000080
    CONTINUE_IF_PC_NEAR        = 0x00000200
    ONCE_PER_DAY               = 0x00000400
    PREFERRED_SPEED_DEFAULT    = 0x00002000  # deprecated
    ALWAYS_SNEAK               = 0x00020000
    ALLOW_SWIMMING             = 0x00040000
    IGNORE_COMBAT              = 0x00100000
    WEAPONS_UNEQUIPPED         = 0x00200000
    WEAPON_DRAWN               = 0x00800000
    NO_COMBAT_ALERT            = 0x08000000
    WEAR_SLEEP_OUTFIT          = 0x20000000


# ─────────────────────────────────────────────────────────
# 18. SOUL LEVEL
# ─────────────────────────────────────────────────────────
class SoulLevel(IntEnum):
    """SLGM/DATA — Soul Size."""
    NONE    = 0
    PETTY   = 1
    LESSER  = 2
    COMMON  = 3
    GREATER = 4
    GRAND   = 5


# ─────────────────────────────────────────────────────────
# 19. HEAD PART TYPE
# ─────────────────────────────────────────────────────────
class HeadPartType(IntEnum):
    """HDPT/DATA — Type of head part."""
    MISC       = 0
    FACE       = 1
    EYES       = 2
    HAIR       = 3
    FACIAL_HAIR = 4
    SCAR       = 5
    EYEBROWS   = 6


# ─────────────────────────────────────────────────────────
# 20. PROJECTILE TYPES
# ─────────────────────────────────────────────────────────
class ProjectileType(IntEnum):
    """PROJ/DATA — Projectile Type."""
    MISSILE     = 0x01
    LOBBER      = 0x02
    BEAM        = 0x04
    FLAME       = 0x08
    CONE        = 0x10
    BARRIER     = 0x20
    ARROW       = 0x40


# ─────────────────────────────────────────────────────────
# 21. GMST VALUE TYPES (по первому символу Editor ID)
# ─────────────────────────────────────────────────────────
GMST_VALUE_TYPE: Dict[str, str] = {
    "b": "bool (uint32: 0 or 1)",
    "i": "int32",
    "f": "float",
    "s": "string (null-terminated)",
    "u": "uint32 (unsigned)",  # rare
}


# ─────────────────────────────────────────────────────────
# 22. SUBRECORD DATA FORMATS
#     struct format strings для основных подзаписей
#     (big-endian на диске не бывает — всё little-endian)
# ─────────────────────────────────────────────────────────
SUBRECORD_STRUCT_FORMATS: Dict[str, str] = {
    # TES4/HEDR: version (float), numRecords (int32), nextObjectId (int32)
    "HEDR": "<fII",

    # OBND: x1, y1, z1, x2, y2, z2  (6 × int16)
    "OBND": "<hhhhhh",

    # SPIT: cost (uint32), flags (uint32), type (uint32), chargeTime (float),
    #        castType (uint32), delivery (uint32), castDuration (float),
    #        range (float), halfCostPerk (formid)
    "SPIT": "<IIIfIIffI",

    # EFIT: magnitude (float), areaOfEffect (uint32), duration (uint32)
    "EFIT": "<fII",

    # DATA for GLOB: float value
    "GLOB_DATA": "<f",

    # DATA for ALCH: weight (float)
    "ALCH_DATA": "<f",

    # DATA for AMMO: projectile (formid), flags (uint32), damage (float), value (uint32)
    "AMMO_DATA": "<IIfI",

    # DATA for WEAP (partial): see full format in UESP
    # value (int32), weight (float), damage (int16)
    "WEAP_DATA": "<ifh",

    # DATA for ARMO: value (int32), weight (float)
    "ARMO_DATA": "<if",

    # DATA for MISC: value (int32), weight (float)
    "MISC_DATA": "<if",

    # DATA for BOOK: flags (uint8), type (uint8), unused (uint16),
    #                teaches (uint32 — skill/spell formid),
    #                value (uint32), weight (float)
    "BOOK_DATA": "<BBHII f",

    # DATA for LIGH: time (int32), radius (uint32), color (RGBA uint32),
    #                flags (uint32), falloffExponent (float), FOV (float),
    #                nearClip (float), period (float), intensityAmplitude (float),
    #                movementAmplitude (float), value (uint32), weight (float)
    "LIGH_DATA": "<iIIIffffIfIf",

    # LVLO: level (uint16), pad (uint16), reference (formid), count (uint16), pad (uint16)
    "LVLO": "<HHIHH",

    # CNTO: item (formid), count (int32)
    "CNTO": "<Ii",

    # BOD2: firstPersonFlags (uint32), armorType (uint32)
    "BOD2": "<II",

    # ACBS: flags (uint32), magickaOffset (uint16), staminaOffset (uint16),
    #        level (uint16), calcMinLevel (uint16), calcMaxLevel (uint16),
    #        speedMult (uint16), dispositionBase (int16), templateFlags (uint16),
    #        healthOffset (uint16), bleedoutOverride (uint16)
    "ACBS": "<IHHHHHH hHHH",

    # AIDT: aggression (uint8), confidence (uint8), energy (uint8), morality (uint8),
    #        mood (uint8), assistance (uint8), aggroRadiusFlags (uint8), pad (uint8),
    #        warn (uint32), warnAttack (uint32), attack (uint32)
    "AIDT": "<BBBBBBBB III",

    # CTDA: type (uint8), pad3 (3 bytes), comparisonValue (float or formid),
    #        functionIndex (uint16), pad (uint16), param1 (uint32), param2 (uint32),
    #        runOn (uint32), reference (formid), unknown (int32)
    "CTDA": "<B3sfHHIIIIi",

    # XTEL: destDoor (formid), posX (float), posY (float), posZ (float),
    #        rotX (float), rotY (float), rotZ (float), flags (uint32)
    "XTEL": "<I ffffff I",

    # XLOC: level (uint8), pad3 (3 bytes), key (formid), flags (uint8), pad3 (3 bytes),
    #        unknown (uint32) — Skyrim variant
    "XLOC": "<B3sIB3sI",

    # XESP: parent (formid), flags (uint32)
    "XESP": "<II",

    # XSCL: scale (float)
    "XSCL": "<f",

    # Position/Rotation in REFR/ACHR (DATA subrecord):
    #   posX, posY, posZ, rotX, rotY, rotZ (6 × float)
    "REFR_DATA": "<ffffff",

    # XCLC: gridX (int32), gridY (int32), flags (uint32)
    "XCLC": "<iiI",

    # MNAM in WRLD: usableDimX (int32), usableDimY (int32),
    #   NW cell X (int16), NW cell Y (int16), SE cell X (int16), SE cell Y (int16)
    "WRLD_MNAM": "<ii hhhh",
}


# ─────────────────────────────────────────────────────────
# 23. MAGIC EFFECT FLAGS
# ─────────────────────────────────────────────────────────
class MagicEffectFlag(IntFlag):
    """MGEF — Magic Effect Flags (uint32 in DATA subrecord)."""
    NONE                 = 0x00000000
    HOSTILE              = 0x00000001
    RECOVER              = 0x00000002
    DETRIMENTAL          = 0x00000004
    SNAP_TO_NAVMESH      = 0x00000008  # SSE
    NO_HIT_EVENT         = 0x00000010
    DISPEL_WITH_KEYWORDS = 0x00000100
    NO_DURATION          = 0x00000200
    NO_MAGNITUDE         = 0x00000400
    NO_AREA              = 0x00000800
    FX_PERSIST           = 0x00001000
    GORY_VISUALS         = 0x00004000
    HIDE_IN_UI           = 0x00008000
    NO_RECAST            = 0x00020000
    POWER_AFFECTS_MAGNITUDE = 0x00200000
    POWER_AFFECTS_DURATION  = 0x00400000
    PAINLESS             = 0x04000000
    NO_HIT_EFFECT        = 0x08000000
    NO_DEATH_DISPEL      = 0x10000000


# ─────────────────────────────────────────────────────────
# 24. LOCK LEVEL ENUM
# ─────────────────────────────────────────────────────────
class LockLevel(IntEnum):
    """XLOC — Lock difficulty levels."""
    NOVICE     = 1
    APPRENTICE = 25
    ADEPT      = 50
    EXPERT     = 75
    MASTER     = 100
    REQUIRES_KEY = 255


# ─────────────────────────────────────────────────────────
# 25. LIGHT FLAGS
# ─────────────────────────────────────────────────────────
class LightFlag(IntFlag):
    """LIGH/DATA — Light Flags (uint32)."""
    NONE           = 0x00000000
    DYNAMIC        = 0x00000001
    CAN_BE_CARRIED = 0x00000002
    NEGATIVE       = 0x00000004  # Negative light (shadow caster)
    FLICKER        = 0x00000008
    UNKNOWN_04     = 0x00000010
    OFF_BY_DEFAULT = 0x00000020
    FLICKER_SLOW   = 0x00000040
    PULSE          = 0x00000080
    PULSE_SLOW     = 0x00000100
    SPOT_LIGHT     = 0x00000200
    SPOT_SHADOW    = 0x00000400
    HEMISPHERE     = 0x00000800
    OMNIDIRECTIONAL = 0x00001000
    PORTAL_STRICT  = 0x00002000


# ─────────────────────────────────────────────────────────
# 26. FORM TYPE → human label  (for GetFormType conditions)
# ─────────────────────────────────────────────────────────
FORM_TYPE_ENUM: Dict[int, str] = {
    0:  "NONE",
    1:  "TES4",
    2:  "GRUP",
    3:  "GMST",
    4:  "KYWD",
    5:  "LCRT",
    6:  "AACT",
    7:  "TXST",
    8:  "MICN",
    9:  "GLOB",
    10: "CLAS",
    11: "FACT",
    12: "HDPT",
    13: "EYES",
    14: "RACE",
    15: "SOUN",
    16: "ASPC",
    17: "SKIL",  # unused in Skyrim
    18: "MGEF",
    19: "SCPT",
    20: "LTEX",
    21: "ENCH",
    22: "SPEL",
    23: "SCRL",
    24: "ACTI",
    25: "TACT",
    26: "ARMO",
    27: "BOOK",
    28: "CONT",
    29: "DOOR",
    30: "INGR",
    31: "LIGH",
    32: "MISC",
    33: "APPA",
    34: "STAT",
    35: "MSTT",
    36: "GRAS",
    37: "TREE",
    38: "FLOR",
    39: "FURN",
    40: "WEAP",
    41: "AMMO",
    42: "NPC_",
    43: "LVLN",
    44: "KEYM",
    45: "ALCH",
    46: "IDLM",
    47: "NOTE",  # unused in Skyrim
    48: "COBJ",
    49: "PROJ",
    50: "HAZD",
    51: "SLGM",
    52: "LVLI",
    53: "WTHR",
    54: "CLMT",
    55: "SPGD",
    56: "RFCT",
    57: "REGN",
    58: "NAVI",
    59: "CELL",
    60: "REFR",
    61: "ACHR",
    62: "PMIS",
    63: "PARW",  # Placed Arrow
    64: "PGRE",
    65: "PBEA",  # Placed Beam
    66: "PFLA",  # Placed Flame
    67: "PCON",  # Placed Cone/Voice
    68: "PBAR",  # Placed Barrier
    69: "PHZD",
    70: "WRLD",
    71: "LAND",
    72: "NAVM",
    73: "TLOD",  # unused
    74: "DIAL",
    75: "INFO",
    76: "QUST",
    77: "IDLE",
    78: "PACK",
    79: "CSTY",
    80: "LSCR",
    81: "LVSP",
    82: "ANIO",
    83: "WATR",
    84: "EFSH",
    85: "TOFT",  # unused
    86: "EXPL",
    87: "DEBR",
    88: "IMGS",
    89: "IMAD",
    90: "FLST",
    91: "PERK",
    92: "BPTD",
    93: "ADDN",
    94: "AVIF",
    95: "CAMS",
    96: "CPTH",
    97: "VTYP",
    98: "MATT",
    99: "IPCT",
    100: "IPDS",
    101: "ARMA",
    102: "ECZN",
    103: "LCTN",
    104: "MESG",
    105: "RGDL",  # Ragdoll (unused in SSE)
    106: "DOBJ",
    107: "LGTM",
    108: "MUSC",
    109: "FSTP",
    110: "FSTS",
    111: "SMBN",
    112: "SMQN",
    113: "SMEN",
    114: "DLBR",
    115: "MUST",
    116: "DLVW",
    117: "WOOP",
    118: "SHOU",
    119: "EQUP",
    120: "RELA",
    121: "SCEN",
    122: "ASTP",
    123: "OTFT",
    124: "ARTO",
    125: "MATO",
    126: "MOVT",
    127: "SNDR",
    128: "DUAL",
    129: "SNCT",
    130: "SOPM",
    131: "COLL",
    132: "CLFM",
    133: "REVB",
    134: "LENS",
    135: "LSPR",  # unused
    136: "VOLI",
}


# ─────────────────────────────────────────────────────────
# 27. RELATIONSHIP RANK
# ─────────────────────────────────────────────────────────
class RelationshipRank(IntEnum):
    """Relationship ranks (used in RELA, conditions, etc.)."""
    ARCHNEMESIS = -4
    ENEMY       = -3
    FOE         = -2
    RIVAL       = -1
    ACQUAINTANCE = 0
    FRIEND      = 1
    CONFIDANT   = 2
    ALLY        = 3
    LOVER       = 4


# ─────────────────────────────────────────────────────────
# 28. AGGRESSION / CONFIDENCE / MOOD / ASSISTANCE  (AIDT)
# ─────────────────────────────────────────────────────────
class Aggression(IntEnum):
    UNAGGRESSIVE = 0
    AGGRESSIVE   = 1
    VERY_AGGRESSIVE = 2
    FRENZIED     = 3

class Confidence(IntEnum):
    COWARDLY   = 0
    CAUTIOUS   = 1
    AVERAGE    = 2
    BRAVE      = 3
    FOOLHARDY  = 4

class Mood(IntEnum):
    NEUTRAL    = 0
    ANGRY      = 1
    FEAR       = 2
    HAPPY      = 3
    SAD        = 4
    SURPRISED  = 5
    PUZZLED    = 6
    DISGUSTED  = 7

class Assistance(IntEnum):
    HELPS_NOBODY   = 0
    HELPS_ALLIES   = 1
    HELPS_FRIENDS_AND_ALLIES = 2


# ─────────────────────────────────────────────────────────
# 29. FURNITURE FLAGS / MARKERS
# ─────────────────────────────────────────────────────────
class FurnitureEntryType(IntFlag):
    """FURN — Furniture Entry/Animation Type."""
    NONE   = 0x00
    FRONT  = 0x01
    BEHIND = 0x02
    RIGHT  = 0x04
    LEFT   = 0x08
    UP     = 0x10  # (unused)


# ─────────────────────────────────────────────────────────
# 30. ESL (Light Master) FORMID RANGE
# ─────────────────────────────────────────────────────────
ESL_FORMID_RANGE_MIN = 0x800
ESL_FORMID_RANGE_MAX = 0xFFF
ESL_INDEX_MASK = 0x00000FFF


# ─────────────────────────────────────────────────────────
# 31. COMPRESSION
# ─────────────────────────────────────────────────────────
COMPRESSION_FLAG = 0x00040000  # для быстрой проверки (RecordFlag.COMPRESSED)


# ─────────────────────────────────────────────────────────
# 32. REFR FLAGS (placed object specific)
# ─────────────────────────────────────────────────────────
class PlacedObjectFlag(IntFlag):
    """Дополнительные флаги REFR/ACHR в header."""
    NONE                  = 0x00000000
    INITIALLY_DISABLED    = 0x00000800
    PERSISTENT            = 0x00000400
    VISIBLE_WHEN_DISTANT  = 0x00008000
    STARTS_DEAD           = 0x00200000
    NO_AI_ACQUIRE         = 0x02000000
    NAVMESH_FILTER        = 0x04000000
    NAVMESH_BOUNDING_BOX  = 0x08000000
    REFLECTED_BY_AUTO_WATER = 0x10000000
    NAVMESH_GROUND        = 0x40000000


# ─────────────────────────────────────────────────────────
# 33. OBJECT TYPE (for GetIsObjectType condition)
# ─────────────────────────────────────────────────────────
OBJECT_TYPE_ENUM: Dict[int, str] = {
    0:  "None",
    1:  "Activators",
    2:  "Armor",
    3:  "Books",
    4:  "Clothing",  # unused in Skyrim (merged with Armor)
    5:  "Containers",
    6:  "Doors",
    7:  "Ingredients",
    8:  "Lights",
    9:  "Misc",
    10: "Flora",
    11: "Furniture",
    12: "Weapons (Any)",
    13: "Ammo",
    14: "NPCs",
    15: "Creatures",  # unused in Skyrim (use NPC_)
    16: "Keys",
    17: "Alchemy",
    18: "Food",
    19: "Clothing (All)",  # unused
    20: "SoulGems",
    21: "Spells (All)",
    22: "Scrolls",
    23: "Shouts",
}


# ─────────────────────────────────────────────────────────
# 34. SOUND LEVELS (VNAM — detection sound level)
# ─────────────────────────────────────────────────────────
class SoundLevel(IntEnum):
    """Detection sound levels."""
    LOUD      = 0
    NORMAL    = 1
    SILENT    = 2
    VERY_LOUD = 3


# ─────────────────────────────────────────────────────────
# 35. GLOBAL VARIABLE TYPE (FNAM in GLOB)
# ─────────────────────────────────────────────────────────
class GlobalType(IntEnum):
    """GLOB/FNAM — Global variable value type."""
    SHORT = 0  # s — int16 stored as float
    LONG  = 1  # l — int32 stored as float
    FLOAT = 2  # f — float


# ─────────────────────────────────────────────────────────
# 36. SCENE ACTION TYPES
# ─────────────────────────────────────────────────────────
class SceneActionType(IntEnum):
    """SCEN — Scene Action Type (ANAM byte)."""
    DIALOGUE   = 0
    PACKAGE    = 1
    TIMER      = 2
    PLAYER_DIALOGUE = 3
    START_SCENE = 4
    NPC_RESPONSE_DIALOGUE = 5
    RADIO      = 6  # unused in Skyrim


# ─────────────────────────────────────────────────────────
# 37. MOVEMENT TYPE SPEED
# ─────────────────────────────────────────────────────────
class MovementDefaultSpeed(IntEnum):
    """MOVT default speed enum (for NPC/Race movement)."""
    WALK      = 0
    RUN       = 1
    SWIM_WALK = 2  # Swim
    SWIM_RUN  = 3  # Fast Swim
    FLY_WALK  = 4
    FLY_RUN   = 5
    SPRINT    = 6


# ─────────────────────────────────────────────────────────
# 38. EVENT NODE FLAGS (SMEN)
# ─────────────────────────────────────────────────────────
class StoryManagerEventNodeType(IntEnum):
    """SMEN — Story Manager Event Types (common)."""
    INCREASE_LEVEL            = 0
    COMPLETE_QUEST            = 1
    CHANGE_LOCATION           = 2
    CHANGE_RELATIONSHIP_RANK  = 3
    ATTRACT_ASSAULT           = 4
    ATTRACT_MURDER            = 5
    ATTRACT_JAIL              = 6
    CAST_MAGIC                = 7
    ATTRACT_LOCKPICK          = 8
    ATTRACT_TRESPASS          = 9
    ATTRACT_PICKPOCKET        = 10
    NEW_VOICE_POWER           = 11
    INFECT                    = 12
    CRAFT_ITEM                = 13
    DEAD_BODY                 = 14
    PLAYER_CONNECT            = 15
    PLAYER_DISCONNECT         = 16
    ASSAULT_ACTOR             = 17
    KILL_ACTOR                = 18
    SCRIPT_EVENT              = 19
    ATTRACT_WEREWOLF           = 20
    ESCAPE_JAIL               = 21
    SERVED_TIME               = 22


# ─────────────────────────────────────────────────────────
# 39. IMPACT MATERIAL TYPE
# ─────────────────────────────────────────────────────────
class ImpactMaterialType(IntEnum):
    """MATT — Material Types for impacts."""
    STONE        = 0
    DIRT         = 1
    GRASS        = 2
    GLASS        = 3
    METAL        = 4
    WOOD         = 5
    ORGANIC      = 6
    CLOTH        = 7
    WATER        = 8
    HOLLOW_METAL = 9
    ORGANIC_BUG  = 10
    STONESTAIRS  = 11


# ─────────────────────────────────────────────────────────
# 40. FREQUENTLY USED KEYWORD EDITORIDS  (for quick lookup)
# ─────────────────────────────────────────────────────────
COMMON_KEYWORD_EDITORIDS: Dict[int, str] = {
    # FormIDs из Skyrim.esm (hex → human-readable)
    # Оружие
    0x0001E711: "WeapTypeBattleaxe",
    0x0001E712: "WeapTypeBow",
    0x0001E713: "WeapTypeDagger",
    0x0001E714: "WeapTypeGreatsword",
    0x0001E715: "WeapTypeMace",
    0x0001E716: "WeapTypeSword",
    0x0001E717: "WeapTypeWarAxe",
    0x0001E718: "WeapTypeWarhammer",
    0x0006D930: "WeapTypeStaff",

    # Броня
    0x0006BBD2: "ArmorBoots",
    0x0006BBD3: "ArmorCuirass",
    0x0006BBD4: "ArmorGauntlets",
    0x0006BBD5: "ArmorHelmet",
    0x0006BBD6: "ArmorShield",
    0x000A8657: "ArmorClothing",
    0x000A8658: "ArmorHeavy",
    0x000A8659: "ArmorLight",
    0x00010CD0: "ArmorJewelry",
    0x0006C0EC: "ClothingBody",
    0x0006C0ED: "ClothingFeet",
    0x0006C0EE: "ClothingHands",
    0x0006C0EF: "ClothingHead",

    # Материалы (crafting)
    0x000DB5D2: "DaedricSmithing",
    0x0005AD9F: "DragonArmor",
    0x000CB40D: "DwarvenSmithing",
    0x000CB40E: "EbonySmithing",
    0x000CB40F: "ElvenSmithing",
    0x000CB410: "GlassSmithing",
    0x000CB411: "IronSmithing",  # Steel actually
    0x000CB412: "LeatherSmithing",  # not a real perk keyword, but...
    0x000CB413: "OrcishSmithing",
    0x000CB414: "SteelSmithing",
    0x000CB40C: "AdvancedArmors",

    # Alchemy
    0x00042503: "VendorItemFood",
    0x00042504: "VendorItemFoodRaw",
    0x0008CDEB: "VendorItemPotion",
    0x0008CDEC: "VendorItemPoison",
    0x0008CDED: "VendorItemRecipe",  # not real
    0x000914ED: "VendorItemIngredient",
    0x000917E8: "VendorItemKey",
    0x000917E9: "VendorItemScroll",
    0x000937A5: "VendorItemSpellTome",

    # Misc
    0x000A829B: "VendorItemAnimalHide",
    0x000914EC: "VendorItemGem",
    0x000914EE: "VendorItemOreIngot",
    0x000917EA: "VendorItemAnimalPart",
    0x00100E20: "VendorItemDaedricArtifact",  # DLC
}


# ─────────────────────────────────────────────────────────
# 41. SKILL INDICES (for BOOK teaches, NPC_ skills, etc.)
# ─────────────────────────────────────────────────────────
SKILL_ACTOR_VALUES: Dict[int, str] = {
    6:  "One-Handed",
    7:  "Two-Handed",
    8:  "Archery",
    9:  "Block",
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

# Обратная карта: имя навыка → индекс AV
SKILL_NAME_TO_AV: Dict[str, int] = {v: k for k, v in SKILL_ACTOR_VALUES.items()}


# ─────────────────────────────────────────────────────────
# 42. EQUIP SLOT (EQUP record FormIDs from Skyrim.esm)
# ─────────────────────────────────────────────────────────
EQUIP_SLOT_FORMIDS: Dict[int, str] = {
    0x00013F45: "BothHands",
    0x00013F42: "EitherHand",
    0x00013F43: "LeftHand",
    0x00013F44: "RightHand",
    0x00000136: "Voice",
    0x00000141: "Potion",
}


# ─────────────────────────────────────────────────────────
# 43. UTILITY: fast signature → is_complex check
# ─────────────────────────────────────────────────────────

# Записи, которые содержат GRUP вложенных детей
# (CELL, WRLD, DIAL содержат дочерние группы)
RECORDS_WITH_CHILDREN: FrozenSet[str] = frozenset({
    "CELL", "WRLD", "DIAL",
})

# Записи, для которых не нужно парсить subrecords (слишком большие / бинарные)
BINARY_ONLY_RECORDS: FrozenSet[str] = frozenset({
    "LAND", "NAVM", "NAVI",
})
