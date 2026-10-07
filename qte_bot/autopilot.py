"""Automate d'entraînement : E -> menu -> clic difficulté -> QTE -> pause -> recommence.

Logique pure : les observations (ce qui est à l'écran) entrent, les actions (touche, clic) sortent via des
fonctions injectées. Principe « agir puis vérifier » : chaque action attend sa conséquence visible, avec délai
maximal ; trois échecs de suite = arrêt avec une raison lisible, jamais de boucle aveugle.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

Rect = tuple[int, int, int, int]

MENU_TIMEOUT_S = 2.0      # après E, le menu doit apparaître
START_TIMEOUT_S = 6.0     # après le clic, la 1re case QTE doit apparaître
SESSION_END_S = 2.5       # secours : plus aucune case depuis 2.5 s = session terminée (cases espacées de ~0.9 s)
FAIL_END_S = 1.0          # après une case ratée (le jeu arrête la session), marge courte avant de conclure
QTE_BY_DIFFICULTY = {1: 4, 2: 6, 3: 8, 4: 10, 5: 12}  # annoncé par le menu du jeu
RETRY_DELAY_S = 2.0
MAX_FAILURES = 3
DIFFICULTY_NAMES = {1: "Facile", 2: "Moyen", 3: "Difficile", 4: "Très difficile", 5: "Extrême"}


class State(Enum):
    IDLE = "attente"
    WAIT_MENU = "ouverture du menu"
    WAIT_START = "lancement"
    TRAINING = "entraînement"
    COOLDOWN = "pause"
    STOPPED = "arrêté"


@dataclass(frozen=True)
class AutoSettings:
    difficulties: set[int]
    pause_min_s: int  # secondes entières
    pause_max_s: int
    max_sessions: int
    max_minutes: int = 0      # arrêt programmé après N minutes (0 = pas de limite de durée)
    interact_key: str = "e"   # touche « utiliser » du jeu pour ouvrir le menu

    def validate(self) -> None:
        if not self.difficulties or not self.difficulties <= set(DIFFICULTY_NAMES):
            raise ValueError("coche au moins une difficulté (1 à 5)")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (self.pause_min_s, self.pause_max_s)):
            raise ValueError("la pause se règle en secondes entières")
        if not 0 <= self.pause_min_s <= self.pause_max_s <= 3600:
            raise ValueError("pause invalide : il faut 0 <= min <= max <= 3600 s")
        if not 1 <= self.max_sessions <= 10_000:
            raise ValueError("nombre de sessions invalide (1 à 10000)")
        if not 0 <= self.max_minutes <= 24 * 60:
            raise ValueError("durée max invalide (0 à 1440 minutes, 0 = illimité)")
        if len(self.interact_key) != 1 or not self.interact_key.isalnum():
            raise ValueError("la touche d'interaction doit être une seule lettre ou un chiffre")


@dataclass(frozen=True)
class Observation:
    now: float
    foreground: bool          # le jeu est-il la fenêtre active ?
    menu_rows: list[Rect]     # lignes du menu des difficultés, [] si fermé
    qte_visible: bool
    katana_warning: bool


@dataclass
class Autopilot:
    settings: AutoSettings
    press: Callable[[str], None]
    click: Callable[[int, int], None]
    rng: random.Random = field(default_factory=random.Random)
    on_session: Callable[[str, int, float], None] | None = None  # ("start"|"end", difficulté, instant)
    state: State = State.IDLE
    reason: str = ""
    sessions_done: int = 0
    failures: int = 0
    last_difficulty: int | None = None
    _deadline: float = 0.0
    _next_action: float = 0.0
    _last_qte: float = 0.0
    _now: float = 0.0
    _in_front: bool = True
    _started_at: float | None = None
    _session_difficulty: int | None = None  # difficulté choisie par NOUS (None = session lancée à la main)
    _cases_taken: int = 0
    _failed_at: float | None = None

    def __post_init__(self) -> None:
        self.settings.validate()

    def step(self, o: Observation) -> None:
        if self.state is State.STOPPED:
            return
        self._now, self._in_front = o.now, o.foreground
        self._started_at = o.now if self._started_at is None else self._started_at
        if o.katana_warning:
            return self._stop("katana pas en main : sors-le puis relance l'automatisation")
        if not o.foreground:  # jamais de touche ni de clic dans une autre fenêtre
            return
        HANDLERS[self.state](self, o)

    @property
    def status(self) -> str:
        done = f"{self.sessions_done}/{self.settings.max_sessions}"
        if self.state is State.STOPPED:
            return f"arrêté ({self.reason}) · sessions {done}"
        diff = f" · {DIFFICULTY_NAMES[self.last_difficulty]}" if self.last_difficulty else ""
        if not self._in_front:
            return f"en attente du jeu (pas au premier plan) · sessions {done}"
        if self.state is State.COOLDOWN:
            left = max(0, math.ceil(self._deadline - self._now))
            return f"pause : {left} s restantes{diff} · sessions {done}"
        return f"{self.state.value}{diff} · sessions {done}"

    # --- états ---
    def _idle(self, o: Observation) -> None:
        if o.qte_visible:
            return self._enter_training(o.now, mine=False)
        if self._time_is_up(o.now):
            return self._stop(f"durée max de {self.settings.max_minutes} min atteinte")
        if o.menu_rows:
            return self._choose(o)
        if o.now >= self._next_action:
            self.press(self.settings.interact_key)
            self._wait(State.WAIT_MENU, o.now + MENU_TIMEOUT_S)

    def _wait_menu(self, o: Observation) -> None:
        if o.menu_rows:
            self._choose(o)
        elif o.now >= self._deadline:
            self._fail(o.now, "le menu ne s'ouvre pas : es-tu bien dans le cercle ?")

    def _wait_start(self, o: Observation) -> None:
        if o.qte_visible:
            self.failures = 0
            self._enter_training(o.now, mine=True)
        elif o.now >= self._deadline:
            self._fail(o.now, "l'entraînement ne démarre pas après le clic")

    def case_done(self, taken: bool, now: float) -> None:
        """Bilan d'une case (appelé par le moteur) : permet de conclure la session sans attendre."""
        if self.state is not State.TRAINING:
            return
        if taken:
            self._cases_taken += 1
        else:
            self._failed_at = now

    def _training(self, o: Observation) -> None:
        if o.qte_visible:
            self._last_qte = o.now
            self._failed_at = None  # le jeu continue malgré l'échec : on suit
            return
        if not self._session_over(o.now):
            return
        self.sessions_done += 1
        if self._session_difficulty is not None and self.on_session:
            self.on_session("end", self._session_difficulty, o.now)
        self._session_difficulty = None
        if self.sessions_done >= self.settings.max_sessions:
            return self._stop(f"limite de {self.settings.max_sessions} sessions atteinte")
        if self._time_is_up(o.now):
            return self._stop(f"durée max de {self.settings.max_minutes} min atteinte")
        pause = self.rng.randint(self.settings.pause_min_s, self.settings.pause_max_s)  # secondes entières
        self._wait(State.COOLDOWN, o.now + pause)

    def _cooldown(self, o: Observation) -> None:
        if o.now >= self._deadline:
            self.state, self._next_action = State.IDLE, o.now

    # --- outils ---
    def _choose(self, o: Observation) -> None:
        self.last_difficulty = self.rng.choice(sorted(self.settings.difficulties))
        x, y, w, h = o.menu_rows[self.last_difficulty - 1]
        self.click(x + w // 3, y + h // 2)
        self._wait(State.WAIT_START, o.now + START_TIMEOUT_S)

    def _session_over(self, now: float) -> bool:
        expected = QTE_BY_DIFFICULTY.get(self._session_difficulty or 0)
        if expected is not None and self._cases_taken >= expected:
            return True  # toutes les cases annoncées sont prises : inutile d'attendre
        if self._failed_at is not None and now - self._failed_at >= FAIL_END_S:
            return True
        return now - self._last_qte >= SESSION_END_S

    def _enter_training(self, now: float, mine: bool) -> None:
        self.state, self._last_qte = State.TRAINING, now
        self._cases_taken, self._failed_at = 0, None
        self._session_difficulty = self.last_difficulty if mine else None
        if self._session_difficulty is not None and self.on_session:
            self.on_session("start", self._session_difficulty, now)

    def _time_is_up(self, now: float) -> bool:
        limit = self.settings.max_minutes
        return limit > 0 and self._started_at is not None and now - self._started_at >= limit * 60

    def _wait(self, state: State, deadline: float) -> None:
        self.state, self._deadline = state, deadline

    def _fail(self, now: float, reason: str) -> None:
        self.failures += 1
        if self.failures >= MAX_FAILURES:
            return self._stop(reason)
        self.state, self._next_action = State.IDLE, now + RETRY_DELAY_S

    def _stop(self, reason: str) -> None:
        self.state, self.reason = State.STOPPED, reason


HANDLERS: dict[State, Callable[[Autopilot, Observation], None]] = {
    State.IDLE: Autopilot._idle,
    State.WAIT_MENU: Autopilot._wait_menu,
    State.WAIT_START: Autopilot._wait_start,
    State.TRAINING: Autopilot._training,
    State.COOLDOWN: Autopilot._cooldown,
}
