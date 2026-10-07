"""Reconnaissance de l'interface d'entraînement : lignes du menu des difficultés, message « katana »."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from qte_bot.paths import APP_DIR

Rect = tuple[int, int, int, int]

UI_TEMPLATES = APP_DIR / "templates" / "ui"
ROW_COUNT = 5
BAR_MAX_WIDTH = 6         # barre d'accent colorée à gauche de chaque ligne (~4 px)
BAR_HEIGHT = (35, 80)
ROW_PITCH_TOLERANCE = 6   # px : les 5 lignes sont régulièrement espacées
ROW_WIDTH_RATIO = 7.5     # largeur d'une ligne ≈ 7.5 × sa hauteur (431 / 56 sur la capture 1080p)
KATANA_ZONE = (slice(780, 1000), slice(0, 700))  # bas-gauche, interface 2D à taille fixe en 1080p
KATANA_MIN_SCORE = 0.75


def find_difficulty_rows(bgr: np.ndarray) -> list[Rect]:
    """Les 5 lignes du menu (haut -> bas = Facile -> Extrême), ou [] si le menu n'est pas affiché."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] > 120) & (hsv[..., 2] > 120)).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    bars = [(int(x), int(y), int(w), int(h)) for x, y, w, h, _ in stats[1:]
            if w <= BAR_MAX_WIDTH and BAR_HEIGHT[0] <= h <= BAR_HEIGHT[1]]
    column = _aligned_column(bars)
    if column is None:
        return []
    return [(x, y, int(h * ROW_WIDTH_RATIO), h) for x, y, _, h in column]


def _aligned_column(bars: list[Rect]) -> list[Rect] | None:
    """5 barres au même x, de même hauteur et régulièrement espacées : sinon ce n'est pas le menu."""
    for anchor in bars:
        column = sorted((b for b in bars if abs(b[0] - anchor[0]) <= 2 and abs(b[3] - anchor[3]) <= 3),
                        key=lambda b: b[1])
        if len(column) != ROW_COUNT:
            continue
        gaps = np.diff([b[1] for b in column])
        if gaps.max() - gaps.min() <= ROW_PITCH_TOLERANCE and gaps.min() > anchor[3]:
            return column
    return None


TITLE_OFFSET = (-1, -65)       # titre du menu par rapport à la 1re ligne (dx, dy), interface 2D fixe
TITLE_SEARCH = 12              # tolérance de position (px)
TITLE_MIN_SCORE = 0.8


def detect_activity(gray: np.ndarray, first_row: Rect) -> str:
    """« combat » si le titre du menu est ENTRAINEMENT COMBAT, sinon « méditation » (seules activités du jeu)."""
    tpl = _template("menu_combat.png")
    x, y = first_row[0] + TITLE_OFFSET[0], first_row[1] + TITLE_OFFSET[1]
    top, left = max(0, y - TITLE_SEARCH), max(0, x - TITLE_SEARCH)
    zone = gray[top: y + tpl.shape[0] + TITLE_SEARCH, left: x + tpl.shape[1] + TITLE_SEARCH]
    if zone.shape[0] < tpl.shape[0] or zone.shape[1] < tpl.shape[1]:
        return "méditation"
    score = cv2.minMaxLoc(cv2.matchTemplate(zone, tpl, cv2.TM_CCOEFF_NORMED))[1]
    return "combat" if score >= TITLE_MIN_SCORE else "méditation"


def katana_warning_visible(gray: np.ndarray) -> bool:
    tpl = _template("katana_warning.png")
    zone = gray[KATANA_ZONE]
    if zone.shape[0] < tpl.shape[0] or zone.shape[1] < tpl.shape[1]:
        return False
    return cv2.minMaxLoc(cv2.matchTemplate(zone, tpl, cv2.TM_CCOEFF_NORMED))[1] >= KATANA_MIN_SCORE


@lru_cache(maxsize=None)
def _template(name: str) -> np.ndarray:
    image = cv2.imread(str(UI_TEMPLATES / name), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(UI_TEMPLATES / name)
    return image
