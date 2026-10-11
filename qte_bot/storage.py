"""Dossier des données du joueur : préparation au lancement, purge des journaux et captures.

Ne supprime jamais que des fichiers listés explicitement (journaux .txt/.log, images .png) dans le dossier des
données : ni config.json, ni le programme, ni un dossier choisi par erreur.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from qte_bot.paths import AppPaths


def prepare(paths: AppPaths) -> str | None:
    """Crée le dossier des données et y met un config.json s'il n'y en a pas. Renvoie ce qui a été fait.

    Ordre : réglages d'une ancienne version (1.0.x les rangeait à côté de l'exe), sinon réglages par défaut.
    """
    paths.data.mkdir(parents=True, exist_ok=True)
    if paths.config.exists():
        return None
    legacy = paths.app / "config.json"
    if legacy.exists() and legacy.resolve() != paths.config.resolve():
        shutil.copyfile(legacy, paths.config)
        return f"réglages repris de l'ancienne version ({legacy})"
    if not paths.default_config.exists():
        raise FileNotFoundError(f"réglages par défaut introuvables : {paths.default_config}")
    shutil.copyfile(paths.default_config, paths.config)
    return f"premier lancement : réglages par défaut dans {paths.config}"


def _targets(paths: AppPaths) -> list[Path]:
    """Fichiers purgeables (hors journal du programme en cours, traité à part)."""
    found = [p for p in (paths.data / "qte_bot.old.log",) if p.is_file()]
    for folder, patterns in ((paths.captures, ("*.txt", "*.png")), (paths.glyphs, ("*.png",))):
        if folder.is_dir():
            found += [p for pattern in patterns for p in folder.glob(pattern) if p.is_file()]
    return found


def logs_size(paths: AppPaths) -> int:
    """Octets occupés par les journaux et captures (ce que la purge libérerait)."""
    files = _targets(paths) + ([paths.log] if paths.log.is_file() else [])
    return sum(p.stat().st_size for p in files)


@dataclass
class Purged:
    files: int = 0
    freed: int = 0
    failed: list[str] = field(default_factory=list)


def purge(paths: AppPaths) -> Purged:
    """Supprime journaux et captures. Le journal du programme (ouvert en écriture) est vidé, pas supprimé.

    Un fichier verrouillé à cet instant (le moteur écrit une ligne) est signalé dans `failed`, jamais ignoré.
    """
    report = Purged()
    for path in _targets(paths):
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            report.failed.append(f"{path.name} : {exc.strerror or exc}")
            continue
        report.files += 1
        report.freed += size
    if paths.log.is_file():
        try:
            size = paths.log.stat().st_size
            with paths.log.open("r+", encoding="utf-8") as log:
                log.truncate(0)
            report.freed += size
        except OSError as exc:
            report.failed.append(f"{paths.log.name} : {exc.strerror or exc}")
    return report


def human_size(n: int) -> str:
    """1234567 -> « 1,2 Mo »."""
    for unit, scale in (("Mo", 1_000_000), ("Ko", 1_000)):
        if n >= scale:
            return f"{n / scale:.1f} {unit}".replace(".", ",")
    return f"{n} o"
