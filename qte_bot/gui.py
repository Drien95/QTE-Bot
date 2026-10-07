"""Menu de réglage (tkinter, inclus dans Python) : délai d'appui, durée d'appui, pause, bilan en direct."""
from __future__ import annotations

import queue
import time
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from qte_bot.autopilot import DIFFICULTY_NAMES, AutoSettings
from qte_bot.config import Config, save_auto, save_timing
from qte_bot.engine import Engine, Timing
from qte_bot.hud import HudFeed
from qte_bot.textlog import append_line
from qte_bot.recognizer import Recognizer

POLL_MS = 100
MAX_LOG_LINES = 300
SPIN = {"from_": 0, "to": 1000, "increment": 10, "width": 7}


class App:
    def __init__(self, root: tk.Tk, cfg: Config, config_path: Path, engine: Engine):
        self.root, self.config_path, self.engine = root, config_path, engine
        self.events: queue.Queue[str] = queue.Queue()
        engine.emit = self._emit  # le moteur tourne dans un autre thread : passage par une file
        self._event_log = engine.captures_dir / "evenements.txt"
        self.delay_min = tk.IntVar(value=cfg.delay_min_ms)
        self.delay_max = tk.IntVar(value=cfg.delay_max_ms)
        self.hold = tk.IntVar(value=cfg.hold_ms)
        self.message = tk.StringVar()
        self.stats = tk.StringVar()
        self.hud_on = tk.BooleanVar(value=True)
        self.overlay = None  # branché par run_gui si l'affichage a pu être créé
        self._build()

    def _build(self) -> None:
        self.root.title("QTE Bot")
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        self.state_btn = tk.Button(frame, font=("Segoe UI", 12, "bold"), width=22, command=self._toggle)
        self.state_btn.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        ttk.Label(frame, text="Délai avant appui (ms, depuis l'apparition de la case)").grid(row=1, column=0, columnspan=4, sticky="w")
        delays = ttk.Frame(frame)
        delays.grid(row=2, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(delays, text="min").pack(side="left")
        ttk.Spinbox(delays, textvariable=self.delay_min, **SPIN).pack(side="left", padx=(4, 16))
        ttk.Label(delays, text="max").pack(side="left")
        ttk.Spinbox(delays, textvariable=self.delay_max, **SPIN).pack(side="left", padx=4)
        ttk.Label(frame, text="Tiré au hasard entre min et max. Une case reste ~600 ms à l'écran.",
                  foreground="#666").grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 8))
        hold = ttk.Frame(frame)
        hold.grid(row=4, column=0, columnspan=4, sticky="w")
        ttk.Label(hold, text="Durée d'appui (ms)").pack(side="left")
        ttk.Spinbox(hold, textvariable=self.hold, from_=1, to=200, increment=10, width=7).pack(side="left", padx=4)
        ttk.Button(frame, text="Appliquer et enregistrer", command=self._apply).grid(row=5, column=0, columnspan=2, pady=8, sticky="w")
        ttk.Checkbutton(frame, text="Affichage HUD sur l'écran", variable=self.hud_on,
                        command=self._toggle_hud).grid(row=5, column=2, columnspan=2, sticky="e")
        ttk.Label(frame, textvariable=self.message).grid(row=6, column=0, columnspan=4)
        ttk.Label(frame, textvariable=self.stats, font=("Segoe UI", 10, "bold")).grid(row=7, column=0, columnspan=4, pady=6)
        self.auto_panel = AutoPanel(frame, self.engine, self.config_path, self.engine.cfg.auto)
        self.auto_panel.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.log = tk.Text(frame, height=12, width=88, font=("Consolas", 9), state="disabled")
        self.log.grid(row=9, column=0, columnspan=4)
        self._refresh()

    def _emit(self, line: str) -> None:
        """Affiché dans le panneau ET gardé sur disque (horodaté à la ms) pour diagnostiquer après coup."""
        self.events.put(line)
        stamp = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        try:
            append_line(self._event_log, f"{stamp} {line}")
        except OSError as exc:  # disque plein / verrouillé : on le dit, sans bloquer le moteur
            self.events.put(f"(journal non écrit : {exc})")

    def _apply(self) -> None:
        try:
            timing = Timing(self.delay_min.get(), self.delay_max.get(), self.hold.get())
            self.engine.set_timing(timing)  # valide (min <= max, bornes) avant d'appliquer
            save_timing(self.config_path, timing.delay_min_ms, timing.delay_max_ms, timing.hold_ms)
        except (ValueError, tk.TclError) as exc:
            self.message.set(f"Refusé : {exc}")
            return
        self.message.set(f"Appliqué : appui entre {timing.delay_min_ms} et {timing.delay_max_ms} ms, maintenu {timing.hold_ms} ms")

    def _toggle_hud(self) -> None:
        if self.overlay is not None:
            self.overlay.set_visible(self.hud_on.get())

    def hud_status(self) -> str:
        s, t = self.engine.stats, self.engine.timing
        state = "ACTIF" if self.engine.enabled else "PAUSE"
        return (f"◢ QTE·BOT  {state}\n  délai {t.delay_min_ms}–{t.delay_max_ms} ms\n"
                f"  pris {s.taken} · ignorés {s.ignored} · sans appui {s.missed}\n"
                f"  auto : {self.engine.auto.status}")

    def _toggle(self) -> None:
        self.events.put("ACTIF" if self.engine.toggle() else "EN PAUSE")

    def _refresh(self) -> None:
        on = self.engine.enabled
        self.state_btn.config(text="ACTIF  (² pour pause)" if on else "EN PAUSE  (² pour reprendre)",
                              bg="#2e7d32" if on else "#757575", fg="white", activebackground="#1b5e20")
        self.auto_panel.refresh()
        s = self.engine.stats
        self.stats.set(f"Cases : {s.cases}   Pris : {s.taken}   Ignorés : {s.ignored}   Pas d'appui : {s.missed}")

    def poll(self) -> None:
        lines = []
        while not self.events.empty() and len(lines) < MAX_LOG_LINES:
            lines.append(self.events.get_nowait())
        if lines:
            self.log.config(state="normal")
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.delete("1.0", f"end-{MAX_LOG_LINES}l")
            self.log.see("end")
            self.log.config(state="disabled")
        self._refresh()
        self.root.after(POLL_MS, self.poll)


class AutoPanel(ttk.LabelFrame):
    """Automatisation : E -> menu -> difficulté au hasard parmi les cochées -> QTE -> pause -> recommence."""

    def __init__(self, parent: tk.Widget, engine: Engine, config_path: Path, auto: AutoSettings):
        super().__init__(parent, text=" Automatisation de l'entraînement ", padding=8)
        self.engine, self.config_path = engine, config_path
        self.on = tk.BooleanVar(value=False)  # toujours désactivée au lancement : activation volontaire
        self.levels = {d: tk.BooleanVar(value=d in auto.difficulties) for d in DIFFICULTY_NAMES}
        self.pause_min = tk.IntVar(value=auto.pause_min_s)
        self.pause_max = tk.IntVar(value=auto.pause_max_s)
        self.max_sessions = tk.IntVar(value=auto.max_sessions)
        self.status = tk.StringVar()
        self.message = tk.StringVar()
        self._build()

    def _build(self) -> None:
        ttk.Checkbutton(self, text="Activer (reste dans le cercle, katana en main)", variable=self.on,
                        command=self._toggle).grid(row=0, column=0, columnspan=5, sticky="w")
        ttk.Label(self, text="Difficultés (une tirée au hasard à chaque session) :").grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))
        for i, (d, name) in enumerate(DIFFICULTY_NAMES.items()):
            ttk.Checkbutton(self, text=f"{d} {name}", variable=self.levels[d]).grid(row=2, column=i, sticky="w", padx=(0, 6))
        row = ttk.Frame(self)
        row.grid(row=3, column=0, columnspan=5, sticky="w", pady=6)
        ttk.Label(row, text="Pause entre sessions, en secondes : min").pack(side="left")
        ttk.Spinbox(row, textvariable=self.pause_min, from_=0, to=3600, increment=1, width=6).pack(side="left", padx=(4, 8))
        ttk.Label(row, text="max").pack(side="left")
        ttk.Spinbox(row, textvariable=self.pause_max, from_=0, to=3600, increment=1, width=6).pack(side="left", padx=(4, 16))
        ttk.Label(row, text="Sessions max").pack(side="left")
        ttk.Spinbox(row, textvariable=self.max_sessions, from_=1, to=10000, width=6).pack(side="left", padx=4)
        ttk.Button(self, text="Appliquer et enregistrer", command=self._apply).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(self, textvariable=self.message).grid(row=4, column=2, columnspan=3, sticky="w")
        ttk.Label(self, textvariable=self.status, font=("Segoe UI", 9, "bold")).grid(row=5, column=0, columnspan=5, sticky="w", pady=(6, 0))

    def _settings(self) -> AutoSettings:
        settings = AutoSettings({d for d, v in self.levels.items() if v.get()},
                                self.pause_min.get(), self.pause_max.get(), self.max_sessions.get())
        settings.validate()
        return settings

    def _apply(self) -> bool:
        try:
            settings = self._settings()
            self.engine.auto.configure(settings)
            save_auto(self.config_path, settings)
        except (ValueError, tk.TclError) as exc:
            self.message.set(f"Refusé : {exc}")
            return False
        self.message.set("Enregistré")
        return True

    def _toggle(self) -> None:
        if self.on.get() and not self._apply():  # réglages invalides : on n'active pas
            self.on.set(False)
            return
        self.engine.auto.set_enabled(self.on.get())

    def refresh(self) -> None:
        self.status.set(f"État : {self.engine.auto.status}")


def run_gui(cfg: Config, config_path: Path, recognizer: Recognizer, captures_dir: Path) -> int:
    _dpi_aware()  # sinon tkinter et la capture ne parlent pas des mêmes pixels sur écran mis à l'échelle
    feed = HudFeed()
    engine = Engine(cfg, recognizer, captures_dir, hud=feed)
    root = tk.Tk()
    app = App(root, cfg, config_path, engine)
    app.overlay = _start_overlay(root, cfg, feed, app)
    worker = threading.Thread(target=_run_engine, args=(engine, app.events), daemon=True)
    worker.start()

    def close() -> None:
        engine.stop()
        worker.join(timeout=2)
        root.destroy()

    def watch_engine() -> None:
        if worker.is_alive():
            root.after(300, watch_engine)
        elif engine.stopped:  # F10 : arrêt demandé -> on ferme
            close()
        # sinon le moteur a planté : la fenêtre reste ouverte avec l'erreur affichée

    root.protocol("WM_DELETE_WINDOW", close)
    app.poll()
    watch_engine()
    root.mainloop()
    return 0


def _run_engine(engine: Engine, events: queue.Queue[str]) -> None:
    try:
        engine.run()
    except Exception as exc:  # affichée dans le menu au lieu de mourir en silence
        events.put(f"ERREUR moteur : {type(exc).__name__}: {exc}")
        raise


def _start_overlay(root: tk.Tk, cfg: Config, feed: HudFeed, app: App):
    from qte_bot.io_win import capture_region
    from qte_bot.overlay import Overlay

    try:
        return Overlay(root, capture_region(cfg.roi), feed, app.hud_status)
    except OSError as exc:
        app.events.put(f"Affichage HUD désactivé : {exc}")
        app.hud_on.set(False)
        return None


def _dpi_aware() -> None:
    import ctypes

    PER_MONITOR_AWARE = 2
    # E_ACCESSDENIED si déjà réglé (ex. par mss) : c'est le résultat voulu, pas une erreur.
    ctypes.windll.shcore.SetProcessDpiAwareness(PER_MONITOR_AWARE)
