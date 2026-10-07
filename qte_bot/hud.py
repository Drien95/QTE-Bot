"""Modèle de l'affichage « HUD » : quoi dessiner, où, de quelle couleur. Pur et thread-safe, sans tkinter."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum

RESULT_MS = 800      # durée d'affichage du verdict après la disparition de la case
MAX_RESULTS = 8      # borne : jamais plus de N verdicts simultanés à l'écran
Rect = tuple[int, int, int, int]  # x, y, w, h en coordonnées écran


class Phase(Enum):
    SEEN = "seen"          # case repérée, lettre lue
    WAITING = "waiting"    # délai en cours avant l'appui
    PRESSED = "pressed"    # touche envoyée
    TAKEN = "taken"        # verdict : le jeu a pris la touche
    FAILED = "failed"      # verdict : ignoré ou pas d'appui


VERDICT_PHASE = {"PRIS": Phase.TAKEN}  # tout autre verdict = échec


@dataclass(frozen=True)
class Mark:
    rect: Rect
    phase: Phase
    label: str
    progress: float | None = None  # avancement du délai 0..1 (WAITING)
    fade: float = 1.0              # 1 = plein, 0 = disparu (verdicts)


@dataclass(frozen=True)
class _Result:
    rect: Rect
    label: str
    phase: Phase
    at: float


@dataclass(frozen=True)
class HudStatus:
    """Panneau d'état en haut à gauche : données seulement, le dessin est dans overlay.py."""
    qte_on: bool = False
    auto_on: bool = False
    turbo: bool = False
    xp: int = 0
    xp_per_hour: float = 0.0
    taken: int = 0
    cases: int = 0
    auto_state: str = "désactivée"
    progress: tuple[int, int | None, str] | None = None  # (prises, attendues, difficulté)
    sessions: tuple[int, int] | None = None              # (faites, max)


def thousands(value: float) -> str:
    """1785 -> « 1 785 » (espace fine insécable, lisible d'un coup d'œil)."""
    return f"{round(value):,}".replace(",", " ")


class HudFeed:
    """Écrit par le moteur (son thread), lu par l'overlay (thread tkinter)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live: Mark | None = None
        self._results: deque[_Result] = deque(maxlen=MAX_RESULTS)

    def frame(self, rect: Rect | None, letter: str | None, phase: Phase, progress: float | None, now: float) -> None:
        mark = None
        if rect is not None:
            mark = Mark(rect, phase, (letter or "?").upper(), progress)
        with self._lock:
            self._live = mark

    def result(self, rect: Rect, letter: str, verdict: str, now: float) -> None:
        phase = VERDICT_PHASE.get(verdict, Phase.FAILED)
        with self._lock:
            self._results.append(_Result(rect, f"{letter.upper()}  {verdict}", phase, now))

    def marks(self, now: float) -> list[Mark]:
        horizon = RESULT_MS / 1000
        with self._lock:
            live = self._live
            results = [r for r in self._results if now - r.at <= horizon]
        out = [Mark(r.rect, r.phase, r.label, fade=max(0.0, 1 - (now - r.at) / horizon)) for r in results]
        return out + ([live] if live else [])
