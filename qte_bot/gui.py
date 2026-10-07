"""Fenêtre principale : deux tuiles marche/arrêt, statistiques, réglages enregistrés automatiquement."""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path

from qte_bot.autopilot import DIFFICULTY_NAMES, AutoSettings
from qte_bot.config import Config, load_config, save_auto, save_hotkeys, save_repress, save_timing, save_turbo
from qte_bot.engine import Engine, Timing
from qte_bot.hud import HudFeed
from qte_bot.keys import key_label, spec_from_event
from qte_bot.recognizer import Recognizer
from qte_bot.textlog import append_line
from qte_bot.ui import theme as t
from qte_bot.ui import widgets as w

POLL_MS = 100
SAVE_DEBOUNCE_MS = 500   # on enregistre 0,5 s après la dernière modification (pas à chaque flèche)
MAX_LOG_LINES = 300
HOTKEY_ROWS = (("toggle", "QTE marche / pause"), ("auto", "Automatisation marche / arrêt"), ("quit", "Quitter le programme"))


class App:
    def __init__(self, root: tk.Tk, cfg: Config, config_path: Path, engine: Engine):
        self.root, self.config_path, self.engine = root, config_path, engine
        self.events: queue.Queue[str] = queue.Queue()
        engine.emit = self._emit  # le moteur tourne dans un autre thread : passage par une file
        self._event_log = engine.captures_dir / "evenements.txt"
        self._init_vars(cfg)
        self._pending: dict[str, str] = {}   # section -> identifiant du `after` d'enregistrement
        self._capture: tuple[str, w.KeyButton] | None = None
        self.overlay = None  # branché par run_gui si l'affichage a pu être créé
        self._build()

    def _init_vars(self, cfg: Config) -> None:
        a = cfg.auto
        self.delay_min, self.delay_max = tk.IntVar(value=cfg.delay_min_ms), tk.IntVar(value=cfg.delay_max_ms)
        self.hold, self.repress = tk.IntVar(value=cfg.hold_ms), tk.BooleanVar(value=cfg.repress)
        self.levels = {d: tk.BooleanVar(value=d in a.difficulties) for d in DIFFICULTY_NAMES}
        self.pause_min, self.pause_max = tk.IntVar(value=a.pause_min_s), tk.IntVar(value=a.pause_max_s)
        self.max_sessions, self.max_minutes = tk.IntVar(value=a.max_sessions), tk.IntVar(value=a.max_minutes)
        self.interact_key = a.interact_key
        self.hotkey_names = dict(cfg.hotkey_names)
        self.hud_on = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Réglages enregistrés automatiquement")

    # ---------- construction ----------
    def _build(self) -> None:
        self.root.title("QTE Bot")
        self.root.configure(bg=t.BG)
        self.root.resizable(False, False)
        body = tk.Frame(self.root, bg=t.BG, padx=16, pady=14)
        body.pack(fill="both")
        self._header(body)
        self._tiles(body)
        self._stats(body)
        columns = tk.Frame(body, bg=t.BG)
        columns.pack(fill="x")
        left, right = tk.Frame(columns, bg=t.BG), tk.Frame(columns, bg=t.BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self._auto_card(left)
        self._qte_card(right)
        self._keys_card(right)
        self._footer(body)
        self._refresh()
        self.root.after(50, lambda: _dark_title_bar(self.root))

    def _header(self, parent: tk.Frame) -> None:
        head = tk.Frame(parent, bg=t.BG)
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="◢ QTE·BOT", font=t.FONT_TITLE, fg=t.CYAN, bg=t.BG).pack(side="left")
        tk.Label(head, text="Garry's Mod · entraînement", font=t.FONT_SMALL, fg=t.MUTED, bg=t.BG).pack(side="left", padx=10, pady=(6, 0))
        w.check(head, "HUD", self.hud_on, self._toggle_hud).pack(side="right")

    def _tiles(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=t.BG)
        row.pack(fill="x", pady=(0, 10))
        self.qte_tile = w.Tile(row, "QTE", self._toggle_qte)
        self.auto_tile = w.Tile(row, "AUTOMATIQUE", self._toggle_auto)
        self.turbo_tile = w.Tile(row, "⚡ TURBO", self._toggle_turbo)
        self.qte_tile.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.auto_tile.pack(side="left", fill="x", expand=True, padx=5)
        self.turbo_tile.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.auto_state = w.label(parent, "", muted=True)
        self.auto_state.configure(bg=t.BG)
        self.auto_state.pack(anchor="w", pady=(0, 8))

    def _stats(self, parent: tk.Frame) -> None:
        box = w.card(parent, "Statistiques")
        self.stat = {key: w.Stat(box, caption, color) for key, caption, color in (
            ("xp", "XP gagnée", t.CYAN), ("xph", "XP / heure", t.CYAN),
            ("sessions", "sessions réussies", t.GREEN), ("cases", "touches prises", t.GREEN))}
        for i, s in enumerate(self.stat.values()):
            s.grid(row=0, column=i, sticky="w", padx=(0, 22))
        self.detail = w.label(box, "", muted=True)
        self.detail.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def _auto_card(self, parent: tk.Frame) -> None:
        box = w.card(parent, "Automatisation")
        w.label(box, "Difficultés jouées (une au hasard à chaque session)", muted=True).pack(anchor="w")
        chips = tk.Frame(box, bg=t.CARD)
        chips.pack(anchor="w", pady=(4, 10))
        self.chips = [w.Chip(chips, name, t.DIFFICULTY_COLORS[d], self.levels[d], lambda: self._changed("auto"))
                      for d, name in DIFFICULTY_NAMES.items()]
        for c in self.chips:
            c.pack(side="left", padx=(0, 6))
        grid = tk.Frame(box, bg=t.CARD)
        grid.pack(anchor="w")
        self._field(grid, 0, "Pause entre sessions (secondes)", (self.pause_min, self.pause_max), 0, 3600, 1, "auto")
        self._field(grid, 1, "Arrêt après … sessions", (self.max_sessions,), 1, 10000, 1, "auto")
        self._field(grid, 2, "Arrêt après … minutes (0 = jamais)", (self.max_minutes,), 0, 1440, 5, "auto")

    def _qte_card(self, parent: tk.Frame) -> None:
        box = w.card(parent, "QTE")
        grid = tk.Frame(box, bg=t.CARD)
        grid.pack(anchor="w")
        self._field(grid, 0, "Délai avant l'appui (ms, min → max)", (self.delay_min, self.delay_max), 0, 1000, 10, "qte")
        self._field(grid, 1, "Durée de l'appui (ms)", (self.hold,), 1, 200, 5, "qte")
        w.check(box, "Insister : réappuyer tant que la case reste, tenter la lettre probable si elle est douteuse", self.repress,
                lambda: self._changed("qte")).pack(anchor="w", pady=(6, 0))
        w.label(box, "Conseil : délai min ≥ 120 ms, le jeu ignore les appuis trop rapides.", muted=True).pack(anchor="w", pady=(4, 0))

    def _keys_card(self, parent: tk.Frame) -> None:
        box = w.card(parent, "Touches  ·  clique puis appuie sur la touche voulue")
        self.key_buttons: dict[str, w.KeyButton] = {}
        rows = HOTKEY_ROWS + (("interact", "Touche « utiliser » du jeu"),)
        for i, (action, text) in enumerate(rows):
            w.label(box, text).grid(row=i, column=0, sticky="w", pady=2)
            btn = w.KeyButton(box, lambda b, a=action: self._start_capture(a, b))
            btn.grid(row=i, column=1, sticky="e", padx=(20, 0), pady=2)
            self.key_buttons[action] = btn
        self._show_keys()

    def _footer(self, parent: tk.Frame) -> None:
        self.status_label = tk.Label(parent, textvariable=self.status, font=t.FONT_SMALL, fg=t.MUTED, bg=t.BG)
        self.status_label.pack(anchor="w")
        toggle = tk.Label(parent, text="▸ Journal", font=t.FONT_SMALL, fg=t.CYAN, bg=t.BG, cursor="hand2")
        toggle.pack(anchor="w", pady=(6, 0))
        self.log = tk.Text(parent, height=8, width=110, font=t.FONT_MONO, bg=t.CARD, fg=t.MUTED,
                           relief="flat", highlightthickness=0, state="disabled")
        toggle.bind("<Button-1>", lambda _e: self._toggle_log(toggle))

    def _field(self, grid: tk.Frame, row: int, text: str, variables: tuple, low: int, high: int, step: int, section: str) -> None:
        w.label(grid, text).grid(row=row, column=0, sticky="w", pady=3)
        cell = tk.Frame(grid, bg=t.CARD)
        cell.grid(row=row, column=1, sticky="w", padx=(16, 0))
        for i, var in enumerate(variables):
            if i:
                w.label(cell, "→", muted=True).pack(side="left", padx=4)
            w.number(cell, var, low, high, step).pack(side="left")
            var.trace_add("write", lambda *_: self._changed(section))

    # ---------- enregistrement automatique ----------
    def _changed(self, section: str) -> None:
        if section in self._pending:
            self.root.after_cancel(self._pending[section])
        self._pending[section] = self.root.after(SAVE_DEBOUNCE_MS, lambda: self._commit(section))

    def _commit(self, section: str) -> None:
        self._pending.pop(section, None)
        try:
            {"qte": self._commit_qte, "auto": self._commit_auto}[section]()
        except (ValueError, tk.TclError) as exc:
            return self._say(f"⚠ Non enregistré : {exc}", t.RED)
        self._say("✓ Enregistré", t.GREEN)

    def _commit_qte(self) -> None:
        timing = Timing(self.delay_min.get(), self.delay_max.get(), self.hold.get())
        self.engine.set_timing(timing)  # valide les bornes avant tout enregistrement
        save_timing(self.config_path, timing.delay_min_ms, timing.delay_max_ms, timing.hold_ms)
        self.engine.set_repress(self.repress.get())
        save_repress(self.config_path, self.repress.get())

    def _auto_settings(self, interact_key: str | None = None) -> AutoSettings:
        settings = AutoSettings({d for d, v in self.levels.items() if v.get()}, self.pause_min.get(),
                                self.pause_max.get(), self.max_sessions.get(), self.max_minutes.get(),
                                interact_key or self.interact_key)
        settings.validate()
        return settings

    def _commit_auto(self, interact_key: str | None = None) -> None:
        settings = self._auto_settings(interact_key)
        save_auto(self.config_path, settings)  # refuse aussi un conflit avec un raccourci
        self.engine.auto.configure(settings)
        self.interact_key = settings.interact_key

    # ---------- raccourcis ----------
    def _start_capture(self, action: str, button: w.KeyButton) -> None:
        self._capture = (action, button)
        button.show("", waiting=True)
        self.root.bind("<KeyPress>", self._on_key)
        self.root.focus_force()

    def _on_key(self, event: tk.Event) -> None:
        self.root.unbind("<KeyPress>")
        action, _ = self._capture
        self._capture = None
        if event.keysym != "Escape":
            spec = spec_from_event(event.keysym, event.keycode, event.char)
            try:
                self._apply_key(action, spec)
                self._say(f"✓ {key_label(spec)} enregistré", t.GREEN)
            except ValueError as exc:
                self._say(f"⚠ Refusé : {exc}", t.RED)
        self._show_keys()

    def _apply_key(self, action: str, spec: str) -> None:
        if action == "interact":
            if len(spec) != 1:
                raise ValueError("la touche « utiliser » doit être une lettre ou un chiffre")
            return self._commit_auto(spec.lower())
        names = self.hotkey_names | {action: spec}
        save_hotkeys(self.config_path, names)  # valide : touches distinctes, pas une lettre que le bot tape
        self.hotkey_names = names
        self.engine.set_hotkeys(load_config(self.config_path).hotkeys)

    def _show_keys(self) -> None:
        for action, btn in self.key_buttons.items():
            btn.show(self.interact_key.upper() if action == "interact" else key_label(self.hotkey_names[action]))

    # ---------- actions ----------
    def _toggle_qte(self) -> None:
        self.engine.toggle()

    def _toggle_auto(self) -> None:
        if not self.engine.auto.enabled:
            try:
                self._commit_auto()  # n'active jamais avec des réglages invalides
            except ValueError as exc:
                return self._say(f"⚠ {exc}", t.RED)
        self.engine.auto.toggle()

    def _toggle_turbo(self) -> None:
        on = not self.engine.turbo
        self.engine.set_turbo(on)
        try:
            save_turbo(self.config_path, on)
        except ValueError as exc:
            return self._say(f"⚠ {exc}", t.RED)
        self._say("⚡ Turbo : tout au minimum (appui immédiat + insistance, aucune pause)" if on
                  else "Turbo désactivé : tes réglages de délai et de pause s'appliquent", t.AMBER if on else t.MUTED)

    def _toggle_hud(self) -> None:
        if self.overlay is not None:
            self.overlay.set_visible(self.hud_on.get())

    def _toggle_log(self, toggle: tk.Label) -> None:
        if self.log.winfo_ismapped():
            self.log.pack_forget()
            toggle.config(text="▸ Journal")
        else:
            self.log.pack(fill="x", pady=(4, 0))
            toggle.config(text="▾ Journal")

    def _say(self, text: str, color: str) -> None:
        self.status.set(text)
        self.status_label.config(fg=color)

    # ---------- rafraîchissement ----------
    def _refresh(self) -> None:
        names = self.hotkey_names
        qte_on, auto_on = self.engine.enabled, self.engine.auto.enabled
        self.qte_tile.show(qte_on, "actifs" if qte_on else "en pause", key_label(names["toggle"]))
        self.auto_tile.show(auto_on, "en marche" if auto_on else "arrêtée", key_label(names["auto"]), t.CYAN)
        turbo_on = self.engine.turbo
        self.turbo_tile.show(turbo_on, "tout au minimum" if turbo_on else "désactivé", "", t.AMBER)
        self.auto_state.config(text=f"Automatisation : {self.engine.auto.status}")
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        xp, s = self.engine.xp, self.engine.stats
        ok = sum(d.ok for d in xp.by_difficulty.values())
        failed = sum(d.failed for d in xp.by_difficulty.values())
        self.stat["xp"].set(str(xp.total_xp))
        self.stat["xph"].set(f"{xp.xp_per_hour(time.perf_counter()):.0f}")
        self.stat["sessions"].set(f"{ok}/{ok + failed}")
        self.stat["cases"].set(f"{s.taken}/{s.cases}")
        rates = [f"{DIFFICULTY_NAMES[d]} {st.rate:.0%}" for d, st in xp.by_difficulty.items() if st.rate is not None]
        self.detail.config(text=f"Réussite : {' · '.join(rates) or '—'}   ·   sauvées en insistant : {s.rescued}")

    def hud_status(self) -> str:
        xp, timing = self.engine.xp, self.engine.timing
        turbo = "  ⚡TURBO" if self.engine.turbo else ""
        return (f"◢ QTE·BOT  {'ACTIF' if self.engine.enabled else 'PAUSE'}{turbo}\n"
                f"  délai {timing.delay_min_ms}–{timing.delay_max_ms} ms\n"
                f"  XP {xp.total_xp} · {xp.xp_per_hour(time.perf_counter()):.0f}/h\n"
                f"  auto : {self.engine.auto.status}")

    def _emit(self, line: str) -> None:
        """Affiché dans le journal ET gardé sur disque (horodaté à la ms) pour diagnostiquer après coup."""
        self.events.put(line)
        stamp = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        try:
            append_line(self._event_log, f"{stamp} {line}")
        except OSError as exc:  # disque plein / verrouillé : on le dit, sans bloquer le moteur
            self.events.put(f"(journal non écrit : {exc})")

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


def run_gui(cfg: Config, config_path: Path, recognizer: Recognizer, captures_dir: Path) -> int:
    _dpi_aware()  # sinon tkinter et la capture ne parlent pas des mêmes pixels sur écran mis à l'échelle
    feed = HudFeed()
    from qte_bot.io_win import real_io

    engine = Engine(cfg, recognizer, captures_dir, hud=feed, io=real_io())
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
        elif engine.stopped:  # touche « quitter » : arrêt demandé -> on ferme
            close()
        # sinon le moteur a planté : la fenêtre reste ouverte avec l'erreur dans le journal

    root.protocol("WM_DELETE_WINDOW", close)
    app.poll()
    watch_engine()
    root.mainloop()
    return 0


def _run_engine(engine: Engine, events: queue.Queue[str]) -> None:
    try:
        engine.run()
    except Exception as exc:  # affichée dans le journal au lieu de mourir en silence
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


def _dark_title_bar(root: tk.Tk) -> None:
    """Barre de titre sombre (Windows 10 20H1+ / 11) ; sans effet ailleurs."""
    import ctypes

    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    on = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(on), ctypes.sizeof(on))


def _dpi_aware() -> None:
    import ctypes

    PER_MONITOR_AWARE = 2
    # E_ACCESSDENIED si déjà réglé (ex. par mss) : c'est le résultat voulu, pas une erreur.
    ctypes.windll.shcore.SetProcessDpiAwareness(PER_MONITOR_AWARE)
