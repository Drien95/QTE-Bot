"""Moteur temps réel : capture -> détection -> lecture -> appui différé, piloté à chaud (menu ou console)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from qte_bot.auto_driver import AutoDriver
from qte_bot.config import Config
from qte_bot.detector import find_prompt
from qte_bot.episodes import EpisodeLog, Summary
from qte_bot.game_io import GameIo
from qte_bot.hud import HudFeed, Phase
from qte_bot.recognizer import Recognizer
from qte_bot.textlog import append_line
from qte_bot.xp import XpTracker
from qte_bot.tracker import PressTracker

ACCEPTED_MAX_MS = 150  # case disparue moins de 150 ms après l'appui = le jeu a pris la touche
MAX_AUTO_SAVES = 300   # borne : un raté en boucle ne doit pas remplir le disque
INSIST_EVERY_MS = 150  # case encore là après l'appui = pas prise : on réappuie à ce rythme (plafonné)
MAX_UNSURE_GLYPHS = 200  # lettres douteuses gardées pour apprendre des variantes (≈100 octets chacune)
UI_KEY_HOLD_MS = 150   # E d'interaction : un appui de 25 ms (réglage QTE) peut passer entre deux ticks serveur

Emit = Callable[[str], None]


@dataclass
class Stats:
    cases: int = 0
    taken: int = 0     # appui pris par le jeu
    ignored: int = 0   # appui envoyé mais la case est restée
    missed: int = 0    # case vue, pas d'appui (lettre douteuse ou disparue avant le délai)
    rescued: int = 0   # prises grâce au 2e appui

    def record(self, s: Summary) -> str:
        self.cases += 1
        if not s.pressed:
            self.missed += 1
            return "PAS D'APPUI"
        if s.gone_after_press_ms is not None and s.gone_after_press_ms <= ACCEPTED_MAX_MS:
            self.taken += 1
            if s.presses > 1:
                self.rescued += 1
                return "PRIS (insisté)"
            return "PRIS"
        self.ignored += 1
        return "IGNORÉ ?"


@dataclass
class Timing:
    delay_min_ms: int
    delay_max_ms: int
    hold_ms: int


@dataclass
class Engine:
    cfg: Config
    recognizer: Recognizer
    captures_dir: Path
    emit: Emit = print
    stats: Stats = field(default_factory=Stats)
    hud: HudFeed | None = None  # affichage par-dessus le jeu (optionnel)
    io: GameIo | None = None    # accès écran/clavier/souris ; None = le moteur refuse de démarrer

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._timing = Timing(self.cfg.delay_min_ms, self.cfg.delay_max_ms, self.cfg.hold_ms)
        self._enabled = True
        self._stop = threading.Event()
        self._saved = 0
        self._last_frame: np.ndarray | None = None
        self._origin = (0, 0)  # coin haut-gauche de la zone capturée, en coordonnées écran
        self._foreground_warned = False
        self.auto = AutoDriver(self.cfg.auto, self._auto_press, self._auto_click, self._emit_safe, self._on_session)
        self.xp = XpTracker()
        self._repress = self.cfg.repress
        self._turbo = self.cfg.turbo
        self._hotkey_codes = dict(self.cfg.hotkeys)
        self._rebuild = True  # le moteur reconstruit tracker/raccourcis au prochain tour
    # --- pilotage (appelable depuis un autre thread) ---
    def set_timing(self, timing: Timing) -> None:
        PressTracker(1, 1).set_delay(timing.delay_min_ms, timing.delay_max_ms)  # valide ou lève
        with self._lock:
            self._timing = timing

    def set_repress(self, on: bool) -> None:
        with self._lock:
            self._repress, self._rebuild = on, True

    def set_turbo(self, on: bool) -> None:
        with self._lock:
            self._turbo = on

    def set_hotkeys(self, codes: dict[str, int]) -> None:
        with self._lock:
            self._hotkey_codes, self._rebuild = dict(codes), True

    def _on_session(self, kind: str, difficulty: int, now: float) -> None:
        if kind == "start":
            self.xp.start_session(difficulty, now)
            return
        ok = self.xp.end_session(now)
        self.emit(f"session {'RÉUSSIE' if ok else 'ratée'} · XP total {self.xp.total_xp}")

    def toggle(self) -> bool:
        with self._lock:
            self._enabled = not self._enabled
            return self._enabled

    @property
    def timing(self) -> Timing:
        with self._lock:
            return self._timing

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def _emit_safe(self, line: str) -> None:
        self.emit(line)  # self.emit peut être remplacé par le menu après la construction

    def _auto_press(self, key: str) -> None:
        """Touche d'interaction (E) : maintenue comme un humain, l'action « utiliser » passe par le serveur."""
        self._require_io().press_key(key, UI_KEY_HOLD_MS)
        self.emit(f"auto : touche '{key.upper()}' envoyée ({UI_KEY_HOLD_MS} ms)")

    def _auto_click(self, x: int, y: int) -> None:
        with self._lock:
            fast = self._turbo
        self._require_io().click_at(x, y, fast)
        self.emit(f"auto : clic envoyé en ({x}, {y})")

    # --- boucle ---
    def run(self) -> None:
        io = self._require_io()
        grabber = io.make_grabber(self.cfg.roi)
        self._origin = (grabber.region["left"], grabber.region["top"])
        episodes = EpisodeLog(self.cfg.release_frames, self._on_episode)
        period = 1.0 / self.cfg.fps
        tracker = hotkeys = None
        self.emit("prêt : zone surveillée = tout l'écran principal")
        while not self._stop.is_set():
            start = time.perf_counter()
            with self._lock:
                enabled, timing, rebuild = self._enabled, self._timing, self._rebuild
                self._rebuild = False
                repress, codes = self._repress, self._hotkey_codes
            if rebuild:  # réglage changé depuis le menu : on repart d'un état propre
                tracker = self._new_tracker(repress)
                hotkeys = io.make_hotkeys(codes)
            if self._handle_hotkeys(hotkeys.poll()):
                tracker = self._new_tracker(repress)
            if not enabled:  # en pause : ni capture ni CPU consommé
                time.sleep(0.05)
                continue
            tracker.set_delay(timing.delay_min_ms, timing.delay_max_ms)
            self._step(grabber, tracker, episodes, timing, io)
            time.sleep(max(0.0, period - (time.perf_counter() - start)))

    def _new_tracker(self, repress: bool) -> PressTracker:
        return PressTracker(self.cfg.confirm_frames, self.cfg.release_frames,
                            insist_every_ms=INSIST_EVERY_MS if repress else None)

    def _require_io(self) -> GameIo:
        if self.io is None:
            raise RuntimeError("Engine sans io : passe io=io_win.real_io() (menu) ou un faux (tests)")
        return self.io

    def _step(self, grabber, tracker: PressTracker, episodes: EpisodeLog, timing: Timing, io: GameIo) -> None:
        bgra = grabber.grab_bgra()
        gray = cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)
        now = time.perf_counter()
        foreground = self._game_in_front(io.foreground_process())
        prompt = find_prompt(gray, self.cfg.min_side, self.cfg.max_side)
        match = self.recognizer.classify(prompt.glyph, prompt.mask) if prompt else None
        key = tracker.update(match.label if match else None, now, visible=prompt is not None,
                             guess=match.guess if match else None, guess_score=match.score if match else 0.0)
        if key and foreground:  # jamais de touche dans une autre fenêtre (navigateur, visionneuse…)
            io.press_key(key, timing.hold_ms)
        elif key:
            key = None
        episodes.observe(now, gray, prompt, match, key)
        self._last_frame = gray
        self.auto.tick(bgra, gray, self._origin, prompt is not None, foreground, now)
        if self.hud is not None:
            self._publish(prompt, match, key, tracker, now)

    def _publish(self, prompt, match, key: str | None, tracker: PressTracker, now: float) -> None:
        if prompt is None:
            self.hud.frame(None, None, Phase.SEEN, None, now)
            return
        progress = tracker.progress(now)
        if key or tracker.pressed:
            phase = Phase.PRESSED
        elif progress is not None:
            phase = Phase.WAITING
        else:
            phase = Phase.SEEN
        self.hud.frame(self._screen_rect(prompt.box), match.guess, phase, progress, now)

    def _screen_rect(self, box) -> tuple[int, int, int, int]:
        return box.x + self._origin[0], box.y + self._origin[1], box.w, box.h

    def _game_in_front(self, process: str) -> bool:
        ok = process == self.cfg.game_process
        if not ok and not self._foreground_warned:  # prévenir une fois, pas à chaque image
            self.emit(f"jeu pas au premier plan ({process or '?'}) : aucune action envoyée")
        self._foreground_warned = not ok
        return ok

    def _handle_hotkeys(self, actions: set[str]) -> bool:
        """Renvoie True si l'état actif/pause a changé."""
        if "quit" in actions:
            self.stop()
        if "capture" in actions and self._last_frame is not None:
            self.emit(f"image -> {self._save(self._last_frame, 'frame')}")
        if "auto" in actions:
            self.auto.toggle()
        if "toggle" in actions:
            self.emit("QTE ACTIFS" if self.toggle() else "QTE EN PAUSE")
            return True
        return False

    # --- bilan par case ---
    def _on_episode(self, s: Summary) -> None:
        verdict = self.stats.record(s)
        self.xp.record_case(verdict)
        self.auto.case_done(verdict.startswith("PRIS"), time.perf_counter())
        if self.hud is not None:
            self.hud.result(self._screen_rect(s.snapshot.box), s.best.guess, verdict, time.perf_counter())
        if s.pressed:
            detail = f"'{s.pressed}' à +{s.press_after_ms} ms, case partie {s.gone_after_press_ms} ms après"
        else:
            detail = f"'{s.best.guess}' visible {s.visible_ms} ms, {s.recognized}/{s.frames} img reconnues"
        line = f"{time.strftime('%H:%M:%S')} {verdict:<11} {detail} | score {s.best.score:.2f}"
        self.emit(line)
        self._journal(line)
        if s.unsure is not None:
            self._keep_unsure_glyph(*s.unsure)
        if self.cfg.save_captures and self._saved < MAX_AUTO_SAVES:  # diagnostic seulement
            self._save_scene(s, verdict)
            self._saved += 1

    def _keep_unsure_glyph(self, mask: np.ndarray, match) -> None:
        """Lettre que le bot n'a pas su lire : gardée (minuscule) pour en faire un modèle si c'est une variante."""
        folder = self.captures_dir / "lettres"
        if folder.exists() and sum(1 for _ in folder.glob("*.png")) >= MAX_UNSURE_GLYPHS:
            return  # borne globale, sur toutes les sessions
        self._save(mask, f"{match.guess}_{match.score:.2f}_{time.perf_counter_ns() % 10**6}", sub="lettres")

    def _journal(self, line: str) -> None:
        append_line(self.captures_dir / "journal.txt", line)

    def _save(self, image: np.ndarray, stem: str, sub: str = "") -> Path:
        directory = self.captures_dir / sub if sub else self.captures_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{time.strftime('%H%M%S')}_{stem}.png"
        cv2.imwrite(str(path), image)
        return path

    def _save_scene(self, s: Summary, verdict: str) -> None:
        snap, ok = s.snapshot, verdict == "PRIS"
        color = (0, 200, 0) if ok else (0, 0, 255)
        scene = cv2.cvtColor(snap.frame, cv2.COLOR_GRAY2BGR)
        b = snap.box
        cv2.rectangle(scene, (b.x - 3, b.y - 3), (b.x + b.w + 3, b.y + b.h + 3), color, 2)
        text = f"{verdict} | lu '{s.best.guess}' score {s.best.score:.2f}"
        cv2.putText(scene, text, (max(0, b.x - 60), max(15, b.y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        tag = {"PRIS": "pris", "IGNORÉ ?": "ignore"}.get(verdict, "rate")
        self._save(scene, f"{s.best.guess}_{tag}")
        self._save(snap.mask, f"{s.best.guess}_{tag}", sub="lettres")
