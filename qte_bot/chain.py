"""Méditation : une seule case qui ne disparaît pas, les touches s'y enchaînent sans pause.

Règles (différentes du Combat, où une case = une touche) :
- nouvelle lettre lue -> appui après le délai réglé, et au moins MIN_GAP après l'appui précédent ;
- même lettre encore affichée -> nouvel appui seulement REPEAT_GAP après le dernier : assez long pour que la
  capture (1-2 images de retard) ait montré la touche suivante, donc jamais l'ancienne lettre sur la nouvelle
  case ; couvre aussi la lettre répétée (« a » puis « a ») et l'appui ignoré ;
- jamais d'insistance rapide (c'est ce qui faisait échouer la Méditation en Turbo).
"""
from __future__ import annotations

import random

MIN_GAP_S = 0.08
REPEAT_GAP_S = 0.25
MAX_SAME_PRESSES = 8      # même lettre appuyée 8 fois d'affilée : le jeu ne prend plus, on arrête d'insister
CONTINUITY_S = 0.15       # trou toléré (image ratée) ; entre deux cases de Combat il y a >= 0,3 s
COMBAT_GAP_MAX_S = 2.0    # case disparue puis nouvelle case en moins de 2 s = signature du Combat
MAX_DELAY_MS = 1000


class ChainTracker:
    def __init__(self, release_frames: int = 3, rng: random.Random | None = None):
        self._release = release_frames
        self._rng = rng or random.Random()
        self._delay_ms = (0, 0)
        self._reset()

    def set_delay(self, min_ms: int, max_ms: int) -> None:
        if not 0 <= min_ms <= max_ms <= MAX_DELAY_MS:
            raise ValueError(f"délai invalide : il faut 0 <= min <= max <= {MAX_DELAY_MS} ms")
        self._delay_ms = (min_ms, max_ms)

    def update(self, label: str | None, now: float, visible: bool | None = None,
               guess: str | None = None, guess_score: float = 0.0) -> str | None:
        """Même interface que PressTracker. Renvoie la touche à presser maintenant, sinon None."""
        if label is None and not visible:
            self._misses += 1
            if self._misses >= self._release:
                self._reset()
            return None
        self._misses = 0
        if label is None:
            return None  # lettre douteuse sur cette image : on attend une lecture sûre
        if label != self._candidate:
            self._candidate, self._due = label, now + self._delay()
        since_last = now - self._last_at
        if label != self._last_key:
            ready = now >= self._due and since_last >= MIN_GAP_S
        else:
            ready = since_last >= REPEAT_GAP_S and self._same_count < MAX_SAME_PRESSES
        if not ready:
            return None
        self._same_count = self._same_count + 1 if label == self._last_key else 1
        self._last_key, self._last_at = label, now
        return label

    def _delay(self) -> float:
        return self._rng.uniform(*self._delay_ms) / 1000

    def seed(self, last_key: str | None, at: float) -> None:
        """Reprise en cours d'enchaînement (bascule depuis le mode Combat) : la dernière touche vient d'être
        envoyée, ne pas la renvoyer tout de suite."""
        if last_key is not None:
            self._last_key, self._last_at, self._same_count, self._candidate = last_key, at, 1, last_key

    @property
    def pressed(self) -> str | None:
        return self._last_key

    def progress(self, now: float) -> float | None:
        return None

    def _reset(self) -> None:
        self._candidate: str | None = None
        self._due = 0.0
        self._last_key: str | None = None
        self._last_at = float("-inf")
        self._same_count = 0
        self._misses = 0


class ChainDetector:
    """Reconnaît la Méditation à son comportement : la lettre change alors que la case n'a jamais disparu.

    Le mode reste actif d'une session à l'autre (la 1re lettre de la session suivante est donc protégée) et ne
    revient au Combat que sur une signature de Combat : case disparue puis nouvelle case en moins de 2 s.
    """

    def __init__(self) -> None:
        self.chain = False
        self._last_label: str | None = None
        self._last_seen = float("-inf")

    def update(self, visible: bool, label: str | None, now: float) -> None:
        gap = now - self._last_seen
        if not visible:
            return
        continuous = gap <= CONTINUITY_S
        if CONTINUITY_S < gap < COMBAT_GAP_MAX_S:
            self.chain = False  # cases séparées par un court trou : c'est du Combat
        if not continuous:
            self._last_label = None
        if label is not None:
            if continuous and self._last_label is not None and label != self._last_label:
                self.chain = True
            self._last_label = label
        self._last_seen = now
