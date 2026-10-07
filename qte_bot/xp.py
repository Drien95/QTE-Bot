"""Compteur d'XP de l'entraînement : sessions réussies/ratées par difficulté, XP gagnée, XP par heure.

Règle : session réussie = au moins une case et AUCUNE case ratée (le jeu arrête la session au 1er échec ;
le nombre annoncé par le menu est faux : 12 annoncées en Extrême, 11 affichées). XP donnée = hypothèse.
"""
from __future__ import annotations

from dataclasses import dataclass, field


XP_BY_DIFFICULTY = {1: 15, 2: 25, 3: 40, 4: 60, 5: 85}
MEDITATION_MIN_SHARE = 0.7  # Méditation annulée au 1er raté : bien moins de touches que la meilleure = ratée
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
    _activity: str = "combat"
    _chain_presses: int = 0
    _best_meditation: dict[int, int] = field(default_factory=dict)  # difficulté -> plus grand nombre de touches

    def start_session(self, difficulty: int, now: float, activity: str = "combat") -> None:
        if difficulty not in XP_BY_DIFFICULTY:
            raise ValueError(f"difficulté inconnue : {difficulty}")
        self.started_at = now if self.started_at is None else self.started_at
        self._difficulty, self._taken, self._failed = difficulty, 0, False
        self._activity, self._chain_presses = activity, 0

    def record_case(self, verdict: str) -> None:
        if self._difficulty is None:
            return  # case hors session automatique (jeu manuel) : pas comptée
        if verdict.startswith(TAKEN):
            self._taken += 1
        else:
            self._failed = True

    def record_chain(self, presses: int) -> None:
        """Méditation : touches envoyées pendant un enchaînement."""
        if self._difficulty is not None:
            self._chain_presses += presses

    def _meditation_success(self, difficulty: int) -> bool:
        best = self._best_meditation.get(difficulty)
        presses = self._chain_presses
        self._best_meditation[difficulty] = max(best or 0, presses)
        return presses > 0 and (best is None or presses >= MEDITATION_MIN_SHARE * best)

    def end_session(self, now: float) -> bool | None:
        """True = réussie (XP ajoutée), False = ratée, None = aucune session en cours."""
        if self._difficulty is None:
            return None
        d, self._difficulty = self._difficulty, None
        if self._activity == "méditation" or self._chain_presses:  # enchaînement vu, même si le titre a été mal lu
            success = self._meditation_success(d)
        else:
            success = not self._failed and self._taken > 0  # le jeu arrête la session au 1er échec
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
