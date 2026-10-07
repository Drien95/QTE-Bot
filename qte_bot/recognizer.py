"""Identifie la lettre d'un glyphe normalisé par comparaison avec des modèles."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from qte_bot.detector import normalize_glyph

FONT_CANDIDATES = ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf")
FONT_RENDER_SIZE = 64
SHIFT_PX = 2           # tolérance de décalage à taille réelle (lettre dessinée à cheval sur deux pixels)
MAX_SIZE_GAP_PX = 3    # au-delà, tailles trop différentes pour comparer à taille réelle (capture redimensionnée)


@dataclass(frozen=True)
class Template:
    label: str
    image: np.ndarray              # normalisé GLYPH_SIZE² (comparaison quelle que soit l'échelle)
    raw: np.ndarray | None = None  # taille réelle, pour les modèles capturés en jeu


@dataclass(frozen=True)
class Match:
    label: str | None  # None = confiance insuffisante, on n'appuie pas
    score: float
    guess: str = "?"   # meilleure lettre même si refusée (diagnostic)
    margin: float = 0.0  # écart avec la 2e lettre


class Recognizer:
    def __init__(self, templates: list[Template], min_score: float, min_margin: float):
        if not templates:
            raise ValueError("aucun modèle de lettre chargé")
        self._templates = templates
        self._min_score = min_score
        self._min_margin = min_margin

    def classify(self, glyph: np.ndarray, mask: np.ndarray | None = None) -> Match:
        """Meilleur label si son score dépasse le seuil ET bat nettement la 2e lettre.

        `glyph` : lettre normalisée ; `mask` : la même à taille réelle (optionnel) -> comparaison tolérante
        aux décalages d'un ou deux pixels, que la normalisation amplifie (S décalé : 0.42 au lieu de 1.00).
        """
        best: dict[str, float] = {}
        for t in self._templates:
            score = float(cv2.matchTemplate(glyph, t.image, cv2.TM_CCOEFF_NORMED)[0, 0])
            if mask is not None and t.raw is not None:
                score = max(score, shifted_score(mask, t.raw))
            best[t.label] = max(score, best.get(t.label, -1.0))
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        label, score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
        margin = score - runner_up
        accepted = score >= self._min_score and margin >= self._min_margin
        return Match(label if accepted else None, score, label, margin)


def load_templates(directory: Path, allowed: str) -> list[Template]:
    """Modèles capturés en jeu : fichiers `<lettre>.png` ou `<lettre>_<n>.png`."""
    templates = []
    for path in sorted(directory.glob("*.png")):
        label = path.stem.split("_")[0].lower()
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if len(label) == 1 and label in allowed and image is not None:
            binary = np.where(image >= 128, 255, 0).astype(np.uint8)
            templates.append(Template(label, normalize_glyph(binary), raw=binary))
    return templates


def shifted_score(mask: np.ndarray, raw: np.ndarray) -> float:
    """Corrélation max en faisant glisser la plus petite image sur la plus grande (± SHIFT_PX), à taille réelle."""
    if abs(mask.shape[0] - raw.shape[0]) > MAX_SIZE_GAP_PX or abs(mask.shape[1] - raw.shape[1]) > MAX_SIZE_GAP_PX:
        return -1.0
    big, small = (mask, raw) if mask.size >= raw.size else (raw, mask)
    big = cv2.copyMakeBorder(big, SHIFT_PX, SHIFT_PX, SHIFT_PX, SHIFT_PX, cv2.BORDER_CONSTANT, value=0)
    if small.shape[0] > big.shape[0] or small.shape[1] > big.shape[1]:
        return -1.0
    result = cv2.matchTemplate(big.astype(np.float32), small.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    return float(np.nan_to_num(result, nan=-1.0, posinf=-1.0, neginf=-1.0).max())


def font_templates(allowed: str) -> list[Template]:
    """Modèles de secours rendus avec une police système (avant d'avoir capturé ceux du jeu)."""
    font = _load_font()  # minuscule ET majuscule : on ne sait pas laquelle le jeu affiche
    return [Template(ch, _render(variant, font)) for ch in allowed for variant in {ch.lower(), ch.upper()}]


def _load_font() -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, FONT_RENDER_SIZE)
        except OSError:
            continue
    raise RuntimeError(f"aucune police trouvée parmi {FONT_CANDIDATES}")


def _render(ch: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    canvas = Image.new("L", (FONT_RENDER_SIZE * 2, FONT_RENDER_SIZE * 2), 0)
    ImageDraw.Draw(canvas).text((FONT_RENDER_SIZE // 2, FONT_RENDER_SIZE // 4), ch, fill=255, font=font)
    mask = np.where(np.array(canvas) >= 128, 255, 0).astype(np.uint8)
    x, y, w, h = cv2.boundingRect(cv2.findNonZero(mask))
    return normalize_glyph(mask[y:y + h, x:x + w])
