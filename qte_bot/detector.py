"""Repère la case QTE : zone sombre carrée, fermée par un fin trait clair, avec une lettre blanche au centre."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

GLYPH_SIZE = 24          # côté du glyphe normalisé (px)
INNER_MARGIN = 0.18      # part du bord ignorée pour ne garder que le centre de la case
GLYPH_THRESHOLD = 170    # luminance mini d'un pixel de lettre
BORDER_THRESHOLD = 90    # luminance mini du trait qui entoure la case
MAX_INTERIOR_MEDIAN = 100
MIN_FILL = 0.85          # part du rectangle occupée par l'intérieur (carré arrondi ~0.95, rond ~0.65)
MAX_ASPECT_DEVIATION = 0.15
MIN_GLYPH_PIXELS = 12
MAX_GLYPH_FRACTION = 0.2  # une lettre n'occupe qu'une petite part du centre
MAX_CANDIDATES = 64      # borne dure : une frame bruitée ne doit pas faire exploser le coût
_SEAL = np.ones((3, 3), np.uint8)
SEARCH_STEP = 2          # recherche des zones sur un masque réduit de moitié (le trait épaissi à 3 px y survit)


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Prompt:
    box: Box
    glyph: np.ndarray  # GLYPH_SIZE x GLYPH_SIZE, uint8 binaire (0/255)
    mask: np.ndarray   # glyphe binaire à sa taille d'origine (pour créer des modèles)


def find_prompt(gray: np.ndarray, min_side: int, max_side: int) -> Prompt | None:
    """Renvoie la case QTE la plus plausible de l'image en niveaux de gris, ou None."""
    if gray.ndim != 2 or min_side <= 0 or max_side < min_side:
        raise ValueError("find_prompt attend une image 2D et 0 < min_side <= max_side")
    for box in _candidate_boxes(gray, min_side, max_side):
        mask = _extract_glyph(gray, box)
        if mask is not None:
            return Prompt(box, normalize_glyph(mask), mask)
    return None


def _candidate_boxes(gray: np.ndarray, min_side: int, max_side: int) -> list[Box]:
    """Zones sombres entièrement fermées par un trait clair, carrées et bien remplies.

    Le trait de la case ne fait qu'1 px avec des coins arrondis : on l'épaissit à 3 px (bouche les trous
    d'anticrénelage), ce qui permet ensuite de chercher les zones sur un masque réduit de moitié sans jamais
    couper le trait (1 pixel sur 2 d'un trait de 3 px est toujours clair). Coût ÷ 4 sur la partie la plus chère.
    """
    _, bright = cv2.threshold(gray, BORDER_THRESHOLD, 1, cv2.THRESH_BINARY)
    bright = cv2.dilate(bright, _SEAL)
    small = bright[::SEARCH_STEP, ::SEARCH_STEP]
    _, _, stats, _ = cv2.connectedComponentsWithStats(1 - small, connectivity=4)
    x, y, w, h, area = (stats[1:, i].astype(np.int64) for i in range(5))
    w_full, h_full = w * SEARCH_STEP, h * SEARCH_STEP
    keep = ((w_full >= min_side) & (w_full <= max_side) & (h_full >= min_side) & (h_full <= max_side)
            & (np.abs(w - h) <= MAX_ASPECT_DEVIATION * np.maximum(w, h)) & (area >= MIN_FILL * w * h))
    idx = np.flatnonzero(keep)[:MAX_CANDIDATES]
    return [Box(int(x[i]) * SEARCH_STEP, int(y[i]) * SEARCH_STEP, int(w_full[i]), int(h_full[i])) for i in idx]


def _extract_glyph(gray: np.ndarray, box: Box) -> np.ndarray | None:
    mx, my = int(box.w * INNER_MARGIN), int(box.h * INNER_MARGIN)
    inner = gray[box.y + my: box.y + box.h - my, box.x + mx: box.x + box.w - mx]
    if inner.size == 0 or np.median(inner) > MAX_INTERIOR_MEDIAN:
        return None
    mask = (inner >= GLYPH_THRESHOLD).astype(np.uint8) * 255
    points = cv2.findNonZero(mask)
    if points is None or not MIN_GLYPH_PIXELS <= len(points) <= MAX_GLYPH_FRACTION * inner.size:
        return None
    gx, gy, gw, gh = cv2.boundingRect(points)
    if not _is_centered(gx + gw / 2, gy + gh / 2, inner.shape):
        return None
    return mask[gy:gy + gh, gx:gx + gw]


def _is_centered(cx: float, cy: float, shape: tuple[int, int]) -> bool:
    h, w = shape
    return abs(cx - w / 2) <= w * 0.25 and abs(cy - h / 2) <= h * 0.25


def normalize_glyph(mask: np.ndarray) -> np.ndarray:
    """Centre le glyphe dans un carré (en gardant ses proportions) puis le redimensionne."""
    h, w = mask.shape
    side = max(h, w)
    square = np.zeros((side, side), dtype=np.uint8)
    oy, ox = (side - h) // 2, (side - w) // 2
    square[oy:oy + h, ox:ox + w] = mask
    resized = cv2.resize(square, (GLYPH_SIZE, GLYPH_SIZE), interpolation=cv2.INTER_AREA)
    return np.where(resized >= 128, 255, 0).astype(np.uint8)
