"""Branche l'automate sur le moteur : lit l'écran (à cadence réduite), exécute les actions, pilotage à chaud."""
from __future__ import annotations

import threading
from typing import Callable

import cv2
import numpy as np

from qte_bot.autopilot import Autopilot, AutoSettings, Observation, State
from qte_bot.screen_ui import find_difficulty_rows, katana_warning_visible

UI_SCAN_PERIOD_S = 0.2  # menu et message katana : 5 analyses/s suffisent, inutile à chaque image

Press = Callable[[str], None]
Click = Callable[[int, int], None]


class AutoDriver:
    def __init__(self, settings: AutoSettings, press: Press, click: Click, emit: Callable[[str], None],
                 on_session: Callable[[str, int, float], None] | None = None):
        settings.validate()
        self._on_session = on_session
        self._lock = threading.Lock()
        self._settings = settings
        self._press, self._click, self._emit = press, click, emit
        self._pilot: Autopilot | None = None  # None = automatisation désactivée (défaut au lancement)
        self._last_scan = -1.0
        self._rows: list[tuple[int, int, int, int]] = []
        self._katana = False
        self._last_status = ""

    # --- pilotage depuis le menu (autre thread) ---
    def configure(self, settings: AutoSettings) -> None:
        settings.validate()
        with self._lock:
            self._settings = settings
            if self._pilot is not None:  # appliqué à chaud, compteur de sessions conservé
                self._pilot.settings = settings

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            self._pilot = Autopilot(self._settings, self._press, self._click, on_session=self._on_session) if on else None
        self._emit("AUTOMATISATION ACTIVÉE" if on else "Automatisation désactivée")

    @property
    def status(self) -> str:
        with self._lock:
            return "désactivée" if self._pilot is None else self._pilot.status

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._pilot is not None

    def toggle(self) -> bool:
        self.set_enabled(not self.enabled)
        return self.enabled

    @property
    def running(self) -> bool:
        with self._lock:
            return self._pilot is not None and self._pilot.state is not State.STOPPED

    # --- appelé à chaque image par le moteur ---
    def tick(self, bgra: np.ndarray, gray: np.ndarray, origin: tuple[int, int],
             qte_visible: bool, foreground: bool, now: float) -> None:
        with self._lock:
            pilot = self._pilot
        if pilot is None:
            return
        if now - self._last_scan >= UI_SCAN_PERIOD_S:
            self._last_scan = now
            self._rows = [(x + origin[0], y + origin[1], w, h)
                          for x, y, w, h in find_difficulty_rows(cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR))]
            self._katana = katana_warning_visible(gray)
        pilot.step(Observation(now, foreground, self._rows, qte_visible, self._katana))
        if pilot.status != self._last_status:  # une ligne par changement d'état, pas à chaque image
            self._last_status = pilot.status
            self._emit(f"auto : {pilot.status}")
