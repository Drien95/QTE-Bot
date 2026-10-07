"""Compteur d'XP de l'entraînement : sessions réussies/ratées par difficulté, XP gagnée, XP par heure.

Hypothèse (non vérifiée côté serveur) : l'XP n'est donnée que si toutes les cases de la session sont prises
et que leur nombre atteint celui annoncé par le menu.
"""
from __future__ import annotations

from dataclasses import dataclass, field

XP_BY_DIFFICULTY = {1: 15, 2: 25, 3: 40, 4: 60, 5: 85}
QTE_BY_DIFFICULTY = {1: 4, 2: 6, 3: 8, 4: 10, 5: 12}
TAKEN = "PRIS"


@dataclass
class DifficultyStats:
    ok: int = 0
    failed: int = 0

    @property
    def rate(self) -> float | None:
        total = self.ok + self.failed
        return None if total == 0 else self.ok / total


@dataclass
class XpTracker:
    total_xp: int = 0
    by_difficulty: dict[int, DifficultyStats] = field(default_factory=lambda: {d: DifficultyStats() for d in XP_BY_DIFFICULTY})
    started_at: float | None = None
    _difficulty: int | None = None
    _taken: int = 0
    _failed: bool = False

    def start_session(self, difficulty: int, now: float) -> None:
        if difficulty not in XP_BY_DIFFICULTY:
            raise ValueError(f"difficulté inconnue : {difficulty}")
        self.started_at = now if self.started_at is None else self.started_at
        self._difficulty, self._taken, self._failed = difficulty, 0, False

    def record_case(self, verdict: str) -> None:
        if self._difficulty is None:
            return  # case hors session automatique (jeu manuel) : pas comptée
        if verdict.startswith(TAKEN):
            self._taken += 1
        else:
            self._failed = True

    def end_session(self, now: float) -> bool | None:
        """True = réussie (XP ajoutée), False = ratée, None = aucune session en cours."""
        if self._difficulty is None:
            return None
        d, self._difficulty = self._difficulty, None
        success = not self._failed and self._taken >= QTE_BY_DIFFICULTY[d]
        stats = self.by_difficulty[d]
        if success:
            stats.ok += 1
            self.total_xp += XP_BY_DIFFICULTY[d]
        else:
            stats.failed += 1
        return success

    def xp_per_hour(self, now: float) -> float:
        if self.started_at is None or now <= self.started_at:
            return 0.0
        return self.total_xp * 3600 / (now - self.started_at)
