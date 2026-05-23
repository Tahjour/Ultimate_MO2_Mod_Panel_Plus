"""
Модуль определения типов контента модов через битовые флаги.
Использование IntFlag позволяет комбинировать флаги через побитовые операции.
"""

from enum import IntFlag
from typing import List, Tuple


class ContentFlags(IntFlag):
    """
    Битовые флаги для классификации контента модов.

    Преимущества битовой маски:
    - Компактное хранение (один int вместо нескольких bool)
    - Быстрые операции сравнения через AND/OR
    - Легко расширяется новыми типами
    """

    NONE = 0
    TEXTURES = 1 << 0
    MESHES = 1 << 1
    SCRIPTS = 1 << 2
    PLUGINS = 1 << 3
    BSA = 1 << 4
    INTERFACE = 1 << 5
    MUSIC = 1 << 6
    SOUND = 1 << 7
    SKSE = 1 << 8
    DLL = 1 << 9
    CONFIG = 1 << 10

    ASSETS = TEXTURES | MESHES | MUSIC | SOUND | INTERFACE
    CODE = SCRIPTS | DLL | SKSE
    ALL = (
        TEXTURES
        | MESHES
        | SCRIPTS
        | PLUGINS
        | BSA
        | INTERFACE
        | MUSIC
        | SOUND
        | SKSE
        | DLL
        | CONFIG
    )

    @classmethod
    def get_flag_info(cls) -> List[Tuple["ContentFlags", str, str]]:
        """Возвращает информацию о флагах для построения UI."""

        return [
            (cls.PLUGINS, "Plugins", "Game plugins (.esp, .esm, .esl)"),
            (cls.BSA, "Archives", "Resource archives (.bsa, .ba2)"),
            (cls.TEXTURES, "Textures", "Mods containing textures/ folder"),
            (cls.MESHES, "Meshes", "Mods containing meshes/ folder"),
            (cls.INTERFACE, "Interface", "UI/HUD mods (interface/ folder)"),
            (cls.SCRIPTS, "Scripts", "Papyrus scripts (scripts/ folder)"),
            (cls.SKSE, "SKSE", "SKSE plugins and scripts (skse/ folder)"),
            (cls.DLL, "DLL Plugins", "Native code plugins (.dll)"),
            (cls.MUSIC, "Music", "Music mods (music/ folder)"),
            (cls.SOUND, "Sound", "Sound FX/Voice mods (sound/ folder)"),
            (cls.CONFIG, "Configs", "Configuration files (.ini, .toml, .json)"),
        ]

    def describe(self) -> str:
        """Человекочитаемое описание активных флагов."""

        if self == ContentFlags.NONE:
            return "No content"

        parts = []
        for flag, name, _ in self.get_flag_info():
            if self & flag:
                parts.append(name)
        return ", ".join(parts)

