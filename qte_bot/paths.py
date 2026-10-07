"""Dossier de l'application : à côté du .exe une fois empaqueté, racine du projet en développement.

config.json, templates/, captures/ et qte_bot.log vivent tous dans ce dossier : on dézippe, on lance, c'est tout.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
