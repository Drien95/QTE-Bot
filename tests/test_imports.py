"""Chaque module doit au moins s'importer : attrape les erreurs de syntaxe des fichiers non couverts par un test."""
import importlib
from pathlib import Path

import pytest

MODULES = sorted(p.stem for p in (Path(__file__).resolve().parent.parent / "qte_bot").glob("*.py") if p.stem != "__init__")


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(f"qte_bot.{name}")
