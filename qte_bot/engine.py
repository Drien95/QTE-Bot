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
from qte_bot.chain import ChainDetector, ChainTracker
from qte_bot.config import Config
from qte_bot.detector import find_prompt
from qte_bot.episodes import EpisodeLog, Summary
from qte_bot.game_io import GameIo
from qte_bot.hud import HudFeed, Phase
from qte_bot.recognizer import Recognizer
from qte_bot.textlog import append_line
from qte_bot.xp import XpTracker
from qte_bot.tracker import MAX_PRESSES, PressTracker

ACCEPTED_MAX_MS = 150  # case disparue moins de 150 ms après l'appui = le jeu a pris la touche
MAX_AUTO_SAVES = 300   # borne : un raté en boucle ne doit pas remplir le disque
SCENE_MARGIN_PX = 200  # capture de diagnostic recadrée autour de la case (~100 Ko au lieu de ~1,7 Mo)
INSIST_EVERY_MS = 150  # case encore là après l'appui = pas prise : on réappuie à ce rythme (plafonné)
MAX_UNSURE_GLYPHS = 200  # lettres douteuses gardées pour apprendre des variantes (≈100 octets chacune)
OPENCV_THREADS = 1       # mesuré : 1 thread = 60 % d'un cœur, multi-thread = 141 % pour la même cadence
CALM_AFTER_S = 2.0        # aucune case depuis 2 s : on analyse moins souvent…
CALM_PERIOD_S = 1 / 30    # …30 images/s (au pire +16 ms pour voir la 1re case, fenêtre de 500 ms)
UI_KEY_HOLD_MS = 150
# ⚡ Turbo : tout au minimum. Appui dès la 1re image lue, puis réappui dès que possible tant que la case reste.
TURBO_E_HOLD_MS = 100   # E d'interaction : un appui de 25 ms (réglage QTE) peut passer entre deux ticks serveur
# Entre deux appuis, la touche doit rester relâchée assez longtemps pour que le jeu (qui lit l'état des touches
# par tick) voie le relâchement ; sinon il croit la touche tenue et ne compte aucun nouvel appui.
# Mesuré le 08/10 : relâchée ~5 ms (appui 45 ms toutes les 50 ms) -> cases expirées en série.
MIN_RELEASE_MS = 50
BOX_LIFETIME_MS = 700   # case sans bonne touche : disparaît après ~650-780 ms (« PAS D'APPUI … visible »)


def insist_plan(hold_ms: int, turbo: bool) -> tuple[int, int]:
    """(intervalle entre deux appuis en ms, nombre max d'appuis par case). L'intervalle se compte depuis le
    DÉBUT de l'appui : il inclut le temps où la touche est tenue, d'où hold_ms + MIN_RELEASE_MS au minimum."""
    if not turbo:
        return max(INSIST_EVERY_MS, hold_ms + MIN_RELEASE_MS), MAX_PRESSES
    every_ms = hold_ms + MIN_RELEASE_MS
    return every_ms, 1 + BOX_LIFETIME_MS // every_ms  # on insiste pendant toute la vie de la case

Emit = Callable[[str], None]


@dataclass
class Stats:
    cases: int = 0
    taken: int = 0     # appui pris par le jeu
    ignored: int = 0   # appui envoyé mais la case est restée
    missed: int = 0    # case vue, pas d'appui (lettre douteuse ou disparue avant le délai)
    rescued: int = 0   # prises grâce au 2e appui
    chained: int = 0   # touches envoyées en Méditation (enchaînement)

    def record_chain(self, presses: int) -> str:
        """Méditation : la case ne disparaît jamais, on compte les touches envoyées."""
        self.cases += presses
        self.taken += presses
        self.chained += presses
        return "MÉDITATION"

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
        self._save_captures = self.cfg.save_captures
        self._last_frame: np.ndarray | None = None
        self._origin = (0, 0)  # coin haut-gauche de la zone capturée, en coordonnées écran
        self._foreground_warned = False
        self._analysis = None  # (bgra, gris, case, lecture) de la dernière image neuve
        self._chain = ChainDetector()
        self._chain_mode = False  # Méditation : touches enchaînées dans une case qui ne disparaît pas
        self._tracker = None
        self._last_box_at = float("-inf")
        self._last_analysis_at = float("-inf")
        self.auto = AutoDriver(self.cfg.auto, self._auto_press, self._auto_click, self._emit_safe, self._on_session)
        self.auto.set_turbo(self.cfg.turbo)
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

    def set_save_captures(self, on: bool) -> None:
        self._save_captures = on

    def set_turbo(self, on: bool) -> None:
        with self._lock:
            self._turbo, self._rebuild = on, True
        self.auto.set_turbo(on)

    @property
    def turbo(self) -> bool:
        with self._lock:
            return self._turbo

    def set_hotkeys(self, codes: dict[str, int]) -> None:
        with self._lock:
            self._hotkey_codes, self._rebuild = dict(codes), True

    def _on_session(self, kind: str, difficulty: int, now: float, activity: str = "combat") -> None:
        if kind == "start":
            self.xp.start_session(difficulty, now, activity)
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
        hold = TURBO_E_HOLD_MS if self.turbo else UI_KEY_HOLD_MS
        self._require_io().press_key(key, hold)
        self.emit(f"auto : touche '{key.upper()}' envoyée ({hold} ms)")

    def _auto_click(self, x: int, y: int) -> None:
        with self._lock:
            fast = self._turbo
        self._require_io().click_at(x, y, fast)
        self.emit(f"auto : clic envoyé en ({x}, {y})")

    # --- boucle ---
    def run(self) -> None:
        io = self._require_io()
        cv2.setNumThreads(OPENCV_THREADS)
        grabber = io.make_grabber(self.cfg.roi)
        self._origin = (grabber.region["left"], grabber.region["top"])
        episodes = EpisodeLog(self.cfg.release_frames, self._on_episode)
        period = 1.0 / self.cfg.fps
        hotkeys = None
        self.emit(f"prêt : tout l'écran principal surveillé · capture {getattr(grabber, 'kind', '?')}")
        while not self._stop.is_set():
            start = time.perf_counter()
            with self._lock:
                enabled, timing, rebuild = self._enabled, self._timing, self._rebuild
                self._rebuild = False
                repress, codes, turbo = self._repress, self._hotkey_codes, self._turbo
            if rebuild:  # réglage changé depuis le menu : on repart d'un état propre
                self._tracker, self._chain_mode = self._new_tracker(repress, turbo), False
                hotkeys = io.make_hotkeys(codes)
            if self._handle_hotkeys(hotkeys.poll()):
                self._tracker, self._chain_mode = self._new_tracker(repress, turbo), False
            if not enabled:  # en pause : ni capture ni CPU consommé
                time.sleep(0.05)
                continue
            self._step(grabber, episodes, timing, io, repress, turbo)
            time.sleep(max(0.0, period - (time.perf_counter() - start)))

    def _new_tracker(self, repress: bool, turbo: bool) -> PressTracker:
        every_ms, max_presses = insist_plan(self.cfg.hold_ms, turbo)
        if turbo:  # confirmation sur 1 image (lecture fiable à ~1.00), insistance serrée
            return PressTracker(1, self.cfg.release_frames, insist_every_ms=every_ms, max_presses=max_presses)
        return PressTracker(self.cfg.confirm_frames, self.cfg.release_frames,
                            insist_every_ms=every_ms if repress else None, max_presses=max_presses)

    def _require_io(self) -> GameIo:
        if self.io is None:
            raise RuntimeError("Engine sans io : passe io=io_win.real_io() (menu) ou un faux (tests)")
        return self.io

    def _step(self, grabber, episodes: EpisodeLog, timing: Timing, io: GameIo, repress: bool, turbo: bool) -> None:
        now = time.perf_counter()
        bgra = grabber.grab_bgra() if self._time_to_analyse(now) else None
        if bgra is not None or self._analysis is None:  # écran inchangé : on réutilise la dernière analyse
            bgra = bgra if bgra is not None else np.zeros((1, 1, 4), np.uint8)
            gray = cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)
            prompt = find_prompt(gray, self.cfg.min_side, self.cfg.max_side) if gray.size > 1 else None
            match = self.recognizer.classify(prompt.glyph, prompt.mask) if prompt else None
            self._analysis = (bgra, gray, prompt, match)
        bgra, gray, prompt, match = self._analysis
        if prompt is not None:
            self._last_box_at = now
        foreground = self._game_in_front(io.foreground_process())
        self._chain.update(prompt is not None, match.label if match else None, now)
        self._switch_mode(self._chain.chain or self.auto.meditation, repress, turbo, now)
        tracker = self._tracker
        tracker.set_delay(*((0, 0) if turbo else (timing.delay_min_ms, timing.delay_max_ms)))
        key = tracker.update(match.label if match else None, now, visible=prompt is not None,
                             guess=match.guess if match else None, guess_score=match.score if match else 0.0)
        if key and foreground:  # jamais de touche dans une autre fenêtre (navigateur, visionneuse…)
            io.press_key(key, timing.hold_ms)
            if self._chain_mode:  # Méditation : détail de chaque appui, pour comprendre le rythme du jeu
                self.emit(f"  appui '{key.upper()}' (lu {match.guess if match else '?'} {(match.score if match else 0.0):.2f})")
        elif key:
            key = None
        episodes.observe(now, gray, prompt, match, key)
        self._last_frame = gray
        self.auto.tick(bgra, gray, self._origin, prompt is not None, foreground, now)
        if self.hud is not None:
            self._publish(prompt, match, key, tracker, now)

    def _switch_mode(self, chain: bool, repress: bool, turbo: bool, now: float) -> None:
        """Combat (une case = une touche) <-> Méditation (enchaînement) ; reprise sans renvoyer la dernière touche."""
        if chain == self._chain_mode:
            return
        if chain:
            new = ChainTracker(self.cfg.release_frames)
            new.seed(self._tracker.pressed if self._tracker else None, now)
            self.emit("mode Méditation : touches enchaînées (pas d'insistance rapide)")
        else:
            new = self._new_tracker(repress, turbo)
        self._tracker, self._chain_mode = new, chain

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

    def _time_to_analyse(self, now: float) -> bool:
        """Pleine cadence dès qu'une case est apparue récemment ; 30/s au calme (CPU divisé par ~2)."""
        calm = now - self._last_box_at > CALM_AFTER_S
        if calm and now - self._last_analysis_at < CALM_PERIOD_S:
            return False
        self._last_analysis_at = now
        return True

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
        if self._chain_mode:
            return self._on_chain_episode(s)
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
        if self._save_captures and self._saved < MAX_AUTO_SAVES:  # diagnostic seulement
            self._save_scene(s, verdict)
            self._saved += 1

    def _on_chain_episode(self, s: Summary) -> None:
        """Méditation : un « épisode » = tout l'enchaînement. Pas de verdict IGNORÉ (la case reste toujours
        affichée), pas d'échec signalé à l'automate : la fin de session se fait au calme (2,5 s sans case)."""
        verdict = self.stats.record_chain(s.presses)
        self.xp.record_chain(s.presses)
        if self.hud is not None:
            self.hud.result(self._screen_rect(s.snapshot.box), s.best.guess, verdict, time.perf_counter())
        line = f"{time.strftime('%H:%M:%S')} MÉDITATION  {s.presses} touches envoyées, case visible {s.visible_ms} ms"
        self.emit(line)
        self._journal(line)

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
        m = SCENE_MARGIN_PX
        self._save(scene[max(0, b.y - m): b.y + b.h + m, max(0, b.x - m): b.x + b.w + m], f"{s.best.guess}_{tag}")
        self._save(snap.mask, f"{s.best.guess}_{tag}", sub="lettres")
