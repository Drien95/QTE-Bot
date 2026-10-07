"""Tout ce par quoi le moteur touche le vrai système : écran, clavier, souris, fenêtre active, raccourcis.

Injecté dans le moteur (jamais importé par lui) : les tests passent un faux, seuls les vrais points d'entrée
(menu, --console) passent `io_win.real_io()`. Un moteur sans io refuse de démarrer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from qte_bot.config import Roi


class Grabber(Protocol):
    region: dict[str, int]

    def grab_bgra(self) -> np.ndarray: ...


class HotkeyPoller(Protocol):
    def poll(self) -> set[str]: ...


@dataclass(frozen=True)
class GameIo:
    make_grabber: Callable[[Roi], Grabber]
    make_hotkeys: Callable[[dict[str, int]], HotkeyPoller]
    press_key: Callable[[str, int], None]
    click_at: Callable[[int, int], None]
    foreground_process: Callable[[], str]
