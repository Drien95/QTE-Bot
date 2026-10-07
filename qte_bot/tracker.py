"""Décide QUAND et QUOI appuyer pour une case : confirmation, délai, insistance, meilleure supposition."""
from __future__ import annotations

import random
from collections import Counter

MAX_DELAY_MS = 1000
MAX_PRESSES = 5              # par case : on insiste, mais jamais sans fin
FALLBACK_MIN_FRAMES = 3      # supposition stable sur au moins 3 images…
FALLBACK_MIN_SHARE = 0.6     # …et majoritaire (60 %) avant de la tenter
FALLBACK_MIN_SCORE = 0.35    # en dessous, ce n'est plus une lettre plausible


class PressTracker:
    def __init__(self, confirm_frames: int, release_frames: int, rng: random.Random | None = None,
                 insist_every_ms: int | None = None):
        """`insist_every_ms` : tant que la case reste après un appui, réappuyer à ce rythme (MAX_PRESSES au total),
        et tenter la meilleure supposition si la lettre n'est jamais lue avec certitude. None = un seul appui sûr."""
        self._confirm = confirm_frames
        self._release = release_frames
        self._insist = None if insist_every_ms is None else insist_every_ms / 1000
        self._rng = rng or random.Random()
        self._delay_ms = (0, 0)
        self._reset()

    def set_delay(self, min_ms: int, max_ms: int) -> None:
        """Intervalle du délai d'appui, tiré au hasard à chaque case (ms depuis sa 1re apparition)."""
        if not 0 <= min_ms <= max_ms <= MAX_DELAY_MS:
            raise ValueError(f"délai invalide : il faut 0 <= min <= max <= {MAX_DELAY_MS} ms")
        self._delay_ms = (min_ms, max_ms)

    def update(self, label: str | None, now: float, visible: bool | None = None,
               guess: str | None = None, guess_score: float = 0.0) -> str | None:
        """Une image : `label` = lettre lue avec certitude (ou None), `visible` = case présente même si la lettre
        est douteuse, `guess`/`guess_score` = meilleure supposition. Renvoie la touche à presser maintenant."""
        if label is None and not visible:
            self._misses += 1
            if self._misses >= self._release:  # case vraiment disparue : on se réarme
                self._reset()
            return None
        self._misses = 0
        self._box_since = now if self._box_since is None else self._box_since
        if label is None:
            return self._unsure(guess, guess_score, now)
        return self._sure(label, now)

    # --- lecture certaine ---
    def _sure(self, label: str, now: float) -> str | None:
        if label != self._candidate:
            self._candidate, self._streak, self._first_seen, self._due = label, 1, now, None
        else:
            self._streak += 1
        if label == self._pressed:
            return self._insist_again(now)
        if self._due is None and self._streak >= self._confirm:
            self._due = self._first_seen + self._delay()
        return self._press(label, now) if self._due is not None and now >= self._due else None

    # --- lettre douteuse sur cette image ---
    def _unsure(self, guess: str | None, score: float, now: float) -> str | None:
        if self._pressed is not None:
            return self._insist_again(now)
        if self._insist is None or guess is None or score < FALLBACK_MIN_SCORE:
            return None
        self._votes[guess] += 1
        if self._fallback_due is None and self._stable_guess() is not None:
            self._fallback_due = self._box_since + self._delay()
        if self._fallback_due is not None and now >= self._fallback_due and self._stable_guess():
            return self._press(self._stable_guess(), now)
        return None

    def _stable_guess(self) -> str | None:
        total = sum(self._votes.values())
        if total < FALLBACK_MIN_FRAMES:
            return None
        guess, count = self._votes.most_common(1)[0]
        return guess if count / total >= FALLBACK_MIN_SHARE else None

    # --- appuis ---
    def _press(self, key: str, now: float) -> str:
        self._pressed, self._pressed_at, self._presses = key, now, 1
        self._due = self._fallback_due = None
        return key

    def _insist_again(self, now: float) -> str | None:
        """Case toujours affichée après l'appui = pas prise : on réappuie, à rythme régulier, plafonné."""
        if self._insist is None or self._presses >= MAX_PRESSES or now - self._pressed_at < self._insist - 1e-9:
            return None
        self._pressed_at, self._presses = now, self._presses + 1
        return self._pressed

    def _delay(self) -> float:
        return self._rng.uniform(*self._delay_ms) / 1000

    @property
    def pressed(self) -> str | None:
        return self._pressed

    def progress(self, now: float) -> float | None:
        """Avancement 0..1 du délai avant appui, ou None si aucun appui n'est programmé."""
        due, since = (self._due, self._first_seen) if self._due is not None else (self._fallback_due, self._box_since)
        if due is None:
            return None
        span = due - since
        return 1.0 if span <= 0 else min(1.0, max(0.0, (now - since) / span))

    def _reset(self) -> None:
        self._candidate: str | None = None
        self._pressed: str | None = None
        self._streak = 0
        self._misses = 0
        self._first_seen = 0.0
        self._due: float | None = None
        self._pressed_at = 0.0
        self._presses = 0
        self._box_since: float | None = None
        self._votes: Counter[str] = Counter()
        self._fallback_due: float | None = None
