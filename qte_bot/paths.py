"""Où vit quoi. Deux dossiers, deux rôles :

- APP_DIR  : le programme (exe, templates/, config.default.json). Jamais écrit par le programme.
- DATA_DIR : les données du joueur (config.json, journaux, captures/). Le seul dossier où l'on écrit.

Installé (exe PyInstaller) : APP_DIR = dossier de l'exe, DATA_DIR = %LOCALAPPDATA%\\QTE-Bot. Une mise à jour ou
une désinstallation du programme ne touche donc jamais aux réglages.
Développement : les deux = racine du projet (rien ne change pour run.bat).
QTE_BOT_DATA_DIR force DATA_DIR (tests, installation portable).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "QTE-Bot"
DATA_DIR_ENV = "QTE_BOT_DATA_DIR"


def app_dir(frozen: bool, executable: str, source_file: str) -> Path:
    return Path(executable).parent if frozen else Path(source_file).resolve().parent.parent


def data_dir(frozen: bool, app: Path, env: dict[str, str]) -> Path:
    """Dossier des données. Lève RuntimeError plutôt que d'écrire n'importe où si Windows ne le donne pas."""
    if env.get(DATA_DIR_ENV):
        return Path(env[DATA_DIR_ENV])
    if not frozen:
        return app
    local = env.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("variable LOCALAPPDATA absente : impossible de savoir où ranger les réglages")
    return Path(local) / APP_NAME


_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = app_dir(_FROZEN, sys.executable, __file__)
DATA_DIR = data_dir(_FROZEN, APP_DIR, dict(os.environ))


@dataclass(frozen=True)
class AppPaths:
    app: Path
    data: Path

    # --- programme (lecture seule) ---
    @property
    def templates(self) -> Path:
        return self.app / "templates"

    @property
    def default_config(self) -> Path:
        return self.app / "config.default.json"

    # --- données du joueur ---
    @property
    def config(self) -> Path:
        return self.data / "config.json"

    @property
    def log(self) -> Path:
        return self.data / "qte_bot.log"

    @property
    def captures(self) -> Path:
        return self.data / "captures"

    @property
    def glyphs(self) -> Path:
        return self.captures / "lettres"

    @property
    def event_log(self) -> Path:
        return self.captures / "evenements.txt"


PATHS = AppPaths(APP_DIR, DATA_DIR)
