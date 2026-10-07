"""Étiquetage manuel : chaque lettre capturée est affichée, on tape la lettre, elle devient un modèle."""
from __future__ import annotations

from pathlib import Path

import cv2

WINDOW = "Quelle lettre ? (Espace = ignorer, Suppr = jeter, Echap = quitter)"
KEY_SKIP, KEY_DELETE, KEY_QUIT = 32, 0x2E0000, 27  # Suppr renvoyé par waitKeyEx sous Windows
MAX_PER_SESSION = 500


def label_glyphs(source: Path, templates: Path, allowed: str) -> int:
    pending = sorted(source.glob("*.png"))[:MAX_PER_SESSION]
    if not pending:
        print(f"rien à étiqueter dans {source}")
        return 0
    templates.mkdir(exist_ok=True)
    print(f"{len(pending)} lettre(s) à étiqueter. Lettres acceptées : {allowed.upper()}")
    done = 0
    for path in pending:
        decision = _ask(path, allowed)
        if decision == "quit":
            break
        if decision == "delete":
            path.unlink()
        elif decision != "skip":
            path.replace(_next_free(templates, decision))
            done += 1
    cv2.destroyAllWindows()
    print(f"{done} modèle(s) ajouté(s) dans {templates}")
    return 0


def _ask(path: Path, allowed: str) -> str:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return "skip"
    scale = max(1, 200 // max(mask.shape))
    cv2.imshow(WINDOW, cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST))
    while True:  # sort dès qu'une touche valide est pressée ou la fenêtre fermée
        key = cv2.waitKeyEx(0)
        if key in (KEY_QUIT, -1):
            return "quit"
        if key == KEY_SKIP:
            return "skip"
        if key == KEY_DELETE:
            return "delete"
        char = chr(key & 0xFF).lower() if 0 <= key < 0x110000 else ""
        if char and char in allowed:
            return char


def _next_free(directory: Path, letter: str) -> Path:
    for n in range(1, 10_000):
        candidate = directory / f"{letter}_{n}.png"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"trop de modèles pour '{letter}'")
