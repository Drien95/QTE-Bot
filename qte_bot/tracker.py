"""Décide QUAND appuyer : confirmation sur N images, délai depuis la 1re apparition, une seule pression."""
from __future__ import annotations

import random

MAX_DELAY_MS = 1000


class PressTracker:
    def __init__(self, confirm_frames: int, release_frames: int, rng: random.Random | None = None,
                 repress_after_ms: int | None = None):
        """`repress_after_ms` : si la case est encore là ce délai après l'appui, on réappuie UNE fois (None = jamais)."""
        self._confirm = confirm_frames
        self._repress_after = None if repress_after_ms is None else repress_after_ms / 1000
        self._release = release_frames
        self._rng = rng or random.Random()
        self._delay_ms = (0, 0)
        self._reset()

    def set_delay(self, min_ms: int, max_ms: int) -> None:
        """Intervalle du délai d'appui, tiré au hasard à chaque case (ms depuis sa 1re apparition)."""
        if not 0 <= min_ms <= max_ms <= MAX_DELAY_MS:
            raise ValueError(f"délai invalide : il faut 0 <= min <= max <= {MAX_DELAY_MS} ms")
        self._delay_ms = (min_ms, max_ms)

    def update(self, label: str | None, now: float) -> str | None:
        """Lettre vue sur l'image (ou None) à l'instant `now` (s) ; renvoie la touche à presser maintenant."""
        if label is None:
            self._misses += 1
            if self._misses >= self._release:  # case disparue : on se réarme
                self._reset()
            return None
        self._misses = 0
        if label != self._candidate:
            self._candidate, self._streak, self._first_seen, self._due = label, 1, now, None
        else:
            self._streak += 1
        if label == self._pressed:
            return self._maybe_repress(label, now)
        if self._due is None and self._streak >= self._confirm:
            self._due = self._first_seen + self._rng.uniform(*self._delay_ms) / 1000
        if self._due is not None and now >= self._due:
            self._pressed, self._due, self._pressed_at, self._repressed = label, None, now, False
            return label
        return None

    def _maybe_repress(self, label: str, now: float) -> str | None:
        """Case toujours affichée longtemps après l'appui = le jeu ne l'a pas pris : 2e et dernier essai."""
        if self._repress_after is None or self._repressed or now - self._pressed_at < self._repress_after:
            return None
        self._repressed = True
        return label

    @property
    def pressed(self) -> str | None:
        return self._pressed

    def progress(self, now: float) -> float | None:
        """Avancement 0..1 du délai avant appui, ou None si aucun appui n'est programmé."""
        if self._due is None:
            return None
        span = self._due - self._first_seen
        return 1.0 if span <= 0 else min(1.0, max(0.0, (now - self._first_seen) / span))

    def _reset(self) -> None:
        self._candidate: str | None = None
        self._pressed: str | None = None
        self._streak = 0
        self._misses = 0
        self._first_seen = 0.0
        self._due: float | None = None
        self._pressed_at = 0.0
        self._repressed = False
