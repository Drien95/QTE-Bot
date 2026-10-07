"""Tests Windows réels : on injecte la touche et on vérifie ce que Windows en comprend."""
import ctypes
import sys
import threading
import time

import os

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows uniquement")

from qte_bot.io_win import press_key, scancode_for  # noqa: E402

user32 = ctypes.windll.user32 if sys.platform == "win32" else None


@pytest.mark.parametrize("char", list("azeqsdwx"))
def test_scancode_matches_active_layout(char):
    # La touche envoyée doit, selon la disposition active, correspondre à la lettre affichée.
    vk_expected = user32.VkKeyScanW(ord(char)) & 0xFF
    assert user32.MapVirtualKeyW(scancode_for(char), 1) == vk_expected  # MAPVK_VSC_TO_VK


@pytest.mark.skipif(os.environ.get("QTE_LIVE_KEYS") != "1",
                    reason="tape de vraies touches dans la fenêtre active : lancer avec QTE_LIVE_KEYS=1")
@pytest.mark.parametrize("char", list("azqw"))
def test_injected_key_is_seen_as_that_letter(char):
    vk = user32.VkKeyScanW(ord(char)) & 0xFF
    seen = []
    threading.Thread(target=lambda: (time.sleep(0.02), seen.append(user32.GetAsyncKeyState(vk) & 0x8000))).start()
    press_key(char, hold_ms=60)
    time.sleep(0.05)
    assert seen and seen[0], f"Windows n'a pas vu '{char}' enfoncée"
    assert not user32.GetAsyncKeyState(vk) & 0x8000, "touche restée enfoncée"
