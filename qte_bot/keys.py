"""Traduction touche pressée <-> nom de raccourci enregistré dans la config ("F7", "P", "²", "VK:118")."""
from __future__ import annotations

import ctypes
import re

_FKEY = re.compile(r"^F([1-9]|1[0-2])$")
MAPVK_VK_TO_VSC = 0
# Touches « étendues » (navigation, flèches, Windows…) : sans le bit 24, Windows les nomme comme le pavé numérique.
EXTENDED_VKS = {33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 91, 92, 93, 111, 144}


def spec_from_event(keysym: str, keycode: int, char: str) -> str:
    """Événement clavier tkinter (sous Windows, keycode = code virtuel) -> nom de raccourci."""
    if _FKEY.match(keysym):
        return keysym
    if char == "²":
        return "²"
    if len(char) == 1 and char.isascii() and char.isalnum():
        return char.upper()
    return f"VK:{keycode}"


def key_label(spec: str) -> str:
    """Nom lisible d'un raccourci, dans la langue du clavier pour les codes VK."""
    if not spec.upper().startswith("VK:"):
        return spec.upper()
    vk = int(spec[3:])
    scancode = ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    buf = ctypes.create_unicode_buffer(32)
    lparam = (scancode << 16) | ((1 << 24) if vk in EXTENDED_VKS else 0)
    if scancode and ctypes.windll.user32.GetKeyNameTextW(lparam, buf, 32):
        return buf.value
    return spec
