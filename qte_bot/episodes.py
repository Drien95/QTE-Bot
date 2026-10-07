"""Suit chaque apparition de case du début à la fin et en fait un bilan (diagnostic des ratés)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from qte_bot.detector import Box, Prompt
from qte_bot.recognizer import Match


@dataclass(frozen=True)
class Snapshot:
    """Image complète de la zone capturée au meilleur moment de l'apparition."""
    frame: np.ndarray
    box: Box
    glyph: np.ndarray
    mask: np.ndarray  # lettre brute, à sa taille d'origine


@dataclass
class Episode:
    frames: int = 0
    recognized: int = 0
    pressed: str | None = None
    best: Match | None = None
    snapshot: Snapshot | None = None
    votes: dict[str, int] = field(default_factory=dict)
    first_seen: float = 0.0
    last_seen: float = 0.0
    unsure: tuple[np.ndarray, Match] | None = None  # 1re image où la lettre était douteuse (lettre brute)
    pressed_at: float | None = None  # DERNIER appui (un réappui réussi compte comme pris)
    presses: int = 0


@dataclass(frozen=True)
class Summary:
    frames: int
    recognized: int
    pressed: str | None
    best: Match
    votes: dict[str, int]
    snapshot: Snapshot
    visible_ms: float               # durée totale d'affichage de la case
    press_after_ms: float | None    # apparition -> appui (notre réactivité)
    gone_after_press_ms: float | None  # dernier appui -> disparition : court = le jeu a pris la touche
    presses: int = 0
    unsure: tuple[np.ndarray, Match] | None = None  # lettre douteuse : sert à apprendre une variante


class EpisodeLog:
    def __init__(self, release_frames: int, on_end: Callable[[Summary], None]):
        self._release = release_frames
        self._on_end = on_end
        self._current: Episode | None = None
        self._misses = 0

    def observe(self, now: float, frame: np.ndarray, prompt: Prompt | None, match: Match | None,
                pressed: str | None) -> None:
        """`now` en secondes (horloge monotone) ; `pressed` = touche envoyée sur cette image."""
        if prompt is None or match is None:
            self._misses += 1
            if self._current and self._misses >= self._release:
                self._finish()
            return
        self._misses = 0
        ep = self._current = self._current or Episode(first_seen=now)
        ep.last_seen = now
        if pressed:
            ep.pressed_at, ep.presses = now, ep.presses + 1
        ep.frames += 1
        ep.recognized += match.label is not None
        if match.label is None and ep.unsure is None:
            ep.unsure = (prompt.mask.copy(), match)
        ep.votes[match.guess] = ep.votes.get(match.guess, 0) + 1
        ep.pressed = ep.pressed or pressed
        if ep.best is None or match.score > ep.best.score:
            ep.best, ep.snapshot = match, Snapshot(frame.copy(), prompt.box, prompt.glyph.copy(), prompt.mask.copy())

    def _finish(self) -> None:
        ep, self._current = self._current, None
        ms = lambda a, b: round((b - a) * 1000)  # noqa: E731
        pressed = ep.pressed_at
        self._on_end(Summary(ep.frames, ep.recognized, ep.pressed, ep.best, ep.votes, ep.snapshot,
                             visible_ms=ms(ep.first_seen, ep.last_seen),
                             press_after_ms=None if pressed is None else ms(ep.first_seen, pressed),
                             gone_after_press_ms=None if pressed is None else ms(pressed, ep.last_seen),
                             presses=ep.presses, unsure=ep.unsure))
