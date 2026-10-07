"""Affichage « Jarvis » par-dessus le jeu : fenêtre transparente, traversée par la souris, invisible aux captures."""
from __future__ import annotations

import ctypes
import time
import tkinter as tk
from typing import Callable

from qte_bot.hud import HudFeed, HudStatus, Mark, Phase, thousands

FRAME_MS = 33              # ~30 rafraîchissements/s
KEY_COLOR = "#010203"      # couleur rendue transparente (jamais utilisée pour dessiner)
FONT = ("Consolas", 10, "bold")
COLORS = {
    Phase.SEEN: "#00e5ff",     # cyan : case repérée
    Phase.WAITING: "#ffc400",  # ambre : délai en cours
    Phase.PRESSED: "#00e676",  # vert : touche envoyée
    Phase.TAKEN: "#00e676",
    Phase.FAILED: "#ff1744",   # rouge : ignoré / pas d'appui
}
TAGS = {Phase.SEEN: "LOCK", Phase.WAITING: "ARMÉ", Phase.PRESSED: "FEU"}

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004+ : la fenêtre n'apparaît dans aucune capture d'écran


class Overlay:
    def __init__(self, root: tk.Tk, region: dict[str, int], feed: HudFeed, status: Callable[[], HudStatus]):
        self.feed, self.status = feed, status
        self.top = tk.Toplevel(root)
        self.top.title("QTE Bot HUD")  # distinct du menu : la relance doit ramener le MENU au premier plan
        self.top.overrideredirect(True)
        self.top.geometry(f"{region['width']}x{region['height']}+{region['left']}+{region['top']}")
        self.top.configure(bg=KEY_COLOR)
        self.top.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.top, bg=KEY_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.top.update_idletasks()
        _make_ghost(self.top)
        self.top.attributes("-transparentcolor", KEY_COLOR)
        self.visible = True
        self._tick()

    def set_visible(self, visible: bool) -> None:
        self.visible = visible
        self.top.deiconify() if visible else self.top.withdraw()

    def _tick(self) -> None:
        if self.visible:
            self.canvas.delete("all")
            for mark in self.feed.marks(time.perf_counter()):
                _draw_mark(self.canvas, mark)
            _draw_status(self.canvas, self.status())
        self.top.after(FRAME_MS, self._tick)


# --- panneau d'état (haut gauche, sous le panneau « Missions » du jeu) ---
PANEL_X, PANEL_Y, PANEL_W = 16, 108, 290
PANEL_BG, PANEL_EDGE, MUTED, OFF_DOT = "#0b1016", "#1f2a36", "#7d8a99", "#3a4554"
CYAN, GREEN, AMBER = COLORS[Phase.SEEN], COLORS[Phase.TAKEN], COLORS[Phase.WAITING]
F_TITLE, F_SMALL = ("Segoe UI Semibold", 10), ("Segoe UI", 9)
F_BIG, F_MID = ("Consolas", 18, "bold"), ("Consolas", 11, "bold")


def _draw_status(c: tk.Canvas, s: HudStatus) -> None:
    x, y, w = PANEL_X, PANEL_Y, PANEL_W
    height = 128 + (24 if s.progress else 0)
    c.create_rectangle(x, y, x + w, y + height, fill=PANEL_BG, outline=PANEL_EDGE)
    _brackets(c, x, y, x + w, y + height, CYAN, arm=14)
    c.create_text(x + 14, y + 12, anchor="nw", text="◢ QTE·BOT", fill=CYAN, font=F_TITLE)
    if s.turbo:
        c.create_rectangle(x + w - 78, y + 10, x + w - 12, y + 28, fill=AMBER, outline="")
        c.create_text(x + w - 45, y + 19, text="⚡ TURBO", fill=PANEL_BG, font=F_SMALL)
    _dot(c, x + 16, y + 44, s.qte_on, GREEN, "QTE " + ("actifs" if s.qte_on else "en pause"))
    _dot(c, x + 150, y + 44, s.auto_on, CYAN, "AUTO " + ("en marche" if s.auto_on else "arrêtée"))
    c.create_text(x + 14, y + 58, anchor="nw", text=thousands(s.xp), fill=CYAN, font=F_BIG)
    c.create_text(x + 14, y + 84, anchor="nw", text="XP gagnée", fill=MUTED, font=F_SMALL)
    c.create_text(x + 150, y + 64, anchor="nw", text=f"{thousands(s.xp_per_hour)} /h", fill=CYAN, font=F_MID)
    c.create_text(x + 150, y + 84, anchor="nw", text=f"touches {s.taken}/{s.cases}", fill=MUTED, font=F_SMALL)
    row = y + 104
    if s.progress:
        _progress(c, x + 14, row, w - 28, *s.progress)
        row += 24
    c.create_text(x + 14, row, anchor="nw", text=_auto_line(s), fill=MUTED, font=F_SMALL)


def _dot(c: tk.Canvas, x: int, y: int, on: bool, color: str, text: str) -> None:
    c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color if on else OFF_DOT, outline="")
    c.create_text(x + 10, y, anchor="w", text=text, fill="#e6edf3" if on else MUTED, font=F_SMALL)


def _progress(c: tk.Canvas, x: int, y: int, w: int, taken: int, expected: int | None, difficulty: str) -> None:
    """Barre de la session en cours ; sans nombre attendu connu, juste le compteur."""
    label = f"{difficulty}  {taken}/{expected}" if expected else f"{difficulty}  {taken} case(s)"
    c.create_text(x, y, anchor="nw", text=label, fill="#e6edf3", font=F_SMALL)
    bar_y = y + 16
    c.create_rectangle(x, bar_y, x + w, bar_y + 5, fill=PANEL_EDGE, outline="")
    if expected:
        c.create_rectangle(x, bar_y, x + int(w * min(1.0, taken / expected)), bar_y + 5, fill=GREEN, outline="")


def _auto_line(s: HudStatus) -> str:
    if not s.auto_on:
        return "automatisation désactivée"
    done = f"sessions {s.sessions[0]}/{s.sessions[1]}" if s.sessions else ""
    return f"{done}  ·  {s.auto_state}" if done else s.auto_state


def _make_ghost(top: tk.Toplevel) -> None:
    """Clics traversants, hors barre des tâches, jamais au premier plan clavier, exclue des captures."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(top.winfo_id())
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        # Sinon le moteur verrait nos propres cadres dans ses captures : on refuse plutôt que de fausser la détection.
        raise OSError("Windows refuse d'exclure l'affichage des captures (Windows 10 2004+ requis)")


def _draw_mark(c: tk.Canvas, m: Mark) -> None:
    x, y, w, h = m.rect
    color = _dim(COLORS[m.phase], m.fade)
    pad = 8 + int((1 - m.fade) * 14)  # les verdicts s'écartent en s'effaçant
    x0, y0, x1, y1 = x - pad, y - pad, x + w + pad, y + h + pad
    _brackets(c, x0, y0, x1, y1, color, arm=max(10, (x1 - x0) // 4))
    tag = TAGS.get(m.phase, "")
    c.create_text(x0, y0 - 10, anchor="sw", text=f"◢ {m.label}  {tag}".rstrip(), fill=color, font=FONT)
    if m.phase is Phase.WAITING and m.progress is not None:
        r = max(x1 - x0, y1 - y0) / 2 + 8
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-359.9 * m.progress,
                     style="arc", outline=color, width=3)
    if m.phase in (Phase.SEEN, Phase.WAITING):  # repères de visée au milieu des côtés
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        for ax, ay, bx, by in ((mx, y0 - 4, mx, y0 + 4), (mx, y1 - 4, mx, y1 + 4), (x0 - 4, my, x0 + 4, my), (x1 - 4, my, x1 + 4, my)):
            c.create_line(ax, ay, bx, by, fill=color, width=1)


def _brackets(c: tk.Canvas, x0: int, y0: int, x1: int, y1: int, color: str, arm: int) -> None:
    glow = _dim(color, 0.35)
    for width, col in ((5, glow), (2, color)):  # trait large et sombre + trait fin vif = effet lumineux
        for (ax, ay), (dx, dy) in (((x0, y0), (1, 1)), ((x1, y0), (-1, 1)), ((x0, y1), (1, -1)), ((x1, y1), (-1, -1))):
            c.create_line(ax + dx * arm, ay, ax, ay, ax, ay + dy * arm, fill=col, width=width, capstyle="round")


def _dim(hex_color: str, factor: float) -> str:
    """Assombrit vers le noir (pas de transparence partielle possible avec une couleur clé)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    f = max(0.0, min(1.0, factor))
    # plancher à 0x10 : ne jamais retomber sur la couleur clé #010203, qui deviendrait un trou
    return "#%02x%02x%02x" % tuple(max(0x10, int(v * f)) for v in (r, g, b))
