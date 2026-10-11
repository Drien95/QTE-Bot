"""Composants de l'interface, dessinés aux couleurs du thème (tkinter pur, rien à installer)."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from qte_bot.ui import theme as t


def card(parent: tk.Widget, title: str) -> tk.Frame:
    """Carte avec titre ; renvoie le cadre intérieur où placer le contenu."""
    outer = tk.Frame(parent, bg=t.CARD, highlightbackground=t.BORDER, highlightthickness=1)
    outer.pack(fill="x", pady=(0, 10))
    tk.Label(outer, text=title.upper(), bg=t.CARD, fg=t.CYAN, font=t.FONT_BOLD).pack(anchor="w", padx=14, pady=(10, 4))
    inner = tk.Frame(outer, bg=t.CARD)
    inner.pack(fill="x", padx=14, pady=(0, 12))
    return inner


def label(parent: tk.Widget, text: str = "", muted: bool = False, **kw) -> tk.Label:
    return tk.Label(parent, text=text, bg=parent["bg"], fg=t.MUTED if muted else t.TEXT,
                    font=kw.pop("font", t.FONT_SMALL if muted else t.FONT), **kw)


class Tile(tk.Frame):
    """Grosse tuile marche/arrêt : un clic bascule. L'état réel est relu en continu (raccourcis clavier)."""

    def __init__(self, parent: tk.Widget, title: str, on_click: Callable[[], None]):
        super().__init__(parent, bg=t.OFF, cursor="hand2", height=86)
        self.pack_propagate(False)
        self.title = tk.Label(self, text=title, font=t.FONT_TILE, fg="white", bg=t.OFF)
        self.title.pack(anchor="w", padx=14, pady=(12, 0))
        self.sub = tk.Label(self, font=t.FONT_SMALL, fg="white", bg=t.OFF)
        self.sub.pack(anchor="w", padx=14)
        for w in (self, self.title, self.sub):
            w.bind("<Button-1>", lambda _e: on_click())

    def show(self, on: bool, text: str, key: str, color: str = t.GREEN) -> None:
        bg = color if on else t.OFF
        fg = t.BG if on else t.TEXT
        for w in (self, self.title, self.sub):
            w.config(bg=bg)
        self.title.config(fg=fg)
        self.sub.config(fg=fg, text=f"{text}   ·   touche {key}" if key else text)


class Stat(tk.Frame):
    """Chiffre clé avec sa légende."""

    def __init__(self, parent: tk.Widget, caption: str, color: str = t.TEXT):
        super().__init__(parent, bg=t.CARD)
        self.value = tk.Label(self, text="0", font=t.FONT_NUMBER, fg=color, bg=t.CARD)
        self.value.pack(anchor="w")
        tk.Label(self, text=caption, font=t.FONT_SMALL, fg=t.MUTED, bg=t.CARD).pack(anchor="w")

    def set(self, text: str) -> None:
        self.value.config(text=text)


def number(parent: tk.Widget, var: tk.IntVar, low: int, high: int, step: int = 1, width: int = 6) -> tk.Spinbox:
    box = tk.Spinbox(parent, textvariable=var, from_=low, to=high, increment=step, width=width,
                     bg=t.CARD_HI, fg=t.TEXT, insertbackground=t.TEXT, buttonbackground=t.CARD_HI,
                     relief="flat", highlightthickness=1, highlightbackground=t.BORDER,
                     highlightcolor=t.CYAN, font=t.FONT, justify="center")
    return box


class Chip(tk.Label):
    """Pastille cochable (difficulté), à la couleur de la ligne du menu du jeu."""

    def __init__(self, parent: tk.Widget, text: str, color: str, var: tk.BooleanVar, on_change: Callable[[], None]):
        super().__init__(parent, text=text, font=t.FONT_BOLD, cursor="hand2", padx=10, pady=6)
        self.color, self.var, self.on_change = color, var, on_change
        self.bind("<Button-1>", self._toggle)
        self.render()

    def _toggle(self, _e=None) -> None:
        self.var.set(not self.var.get())
        self.render()
        self.on_change()

    def render(self) -> None:
        on = self.var.get()
        self.config(bg=self.color if on else t.CARD_HI, fg=t.BG if on else t.MUTED)


class KeyButton(tk.Label):
    """Affiche une touche ; clic puis appui sur une touche = nouveau raccourci."""

    def __init__(self, parent: tk.Widget, on_capture: Callable[["KeyButton"], None]):
        super().__init__(parent, font=t.FONT_BOLD, bg=t.CARD_HI, fg=t.CYAN, cursor="hand2", width=14, pady=4)
        self.bind("<Button-1>", lambda _e: on_capture(self))

    def show(self, text: str, waiting: bool = False) -> None:
        self.config(text="appuie sur une touche…" if waiting else text, fg=t.AMBER if waiting else t.CYAN)


def check(parent: tk.Widget, text: str, var: tk.BooleanVar, on_change: Callable[[], None]) -> tk.Checkbutton:
    return tk.Checkbutton(parent, text=text, variable=var, command=on_change, bg=parent["bg"], fg=t.TEXT,
                          selectcolor=t.CARD_HI, activebackground=parent["bg"], activeforeground=t.TEXT,
                          font=t.FONT, highlightthickness=0, bd=0)


def button(parent: tk.Widget, text: str, command: Callable[[], None], danger: bool = False) -> tk.Label:
    """Bouton plat (un Label cliquable : rendu identique sur toutes les versions de Windows)."""
    fg = t.RED if danger else t.CYAN
    btn = tk.Label(parent, text=text, font=t.FONT_BOLD, bg=t.CARD_HI, fg=fg, cursor="hand2", padx=10, pady=4)
    btn.bind("<Button-1>", lambda _e: command())
    btn.bind("<Enter>", lambda _e: btn.config(bg=t.BORDER))
    btn.bind("<Leave>", lambda _e: btn.config(bg=t.CARD_HI))
    return btn
