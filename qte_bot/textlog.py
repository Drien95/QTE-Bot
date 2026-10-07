"""Ajout de lignes dans un journal texte, borné en taille (rotation vers un .old.txt)."""
from __future__ import annotations

from pathlib import Path

MAX_BYTES = 1_000_000


def append_line(path: Path, line: str, max_bytes: int = MAX_BYTES) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > max_bytes:
        path.replace(path.with_suffix(".old.txt"))  # on garde un seul ancien fichier : taille totale bornée
    with path.open("a", encoding="utf-8") as log:
        log.write(line + "\n")
