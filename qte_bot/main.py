"""Point d'entrée : menu (par défaut), console, test sur image, étiquetage."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from qte_bot.config import Config, load_config
from qte_bot.paths import PATHS
from qte_bot.detector import find_prompt
from qte_bot.recognizer import Recognizer, font_templates, load_templates

TEMPLATES_DIR = PATHS.templates
CAPTURES_DIR = PATHS.captures
GLYPHS_DIR = PATHS.glyphs  # lettres brutes en attente d'étiquetage (--label)


def build_recognizer(cfg: Config) -> Recognizer:
    learned = load_templates(TEMPLATES_DIR, cfg.allowed_keys)
    covered = {t.label for t in learned}
    fallback = font_templates("".join(ch for ch in cfg.allowed_keys if ch not in covered))
    print(f"modèles : {len(learned)} capturés ({''.join(sorted(covered)) or '-'}), {len(fallback)} police de secours")
    return Recognizer(learned + fallback, cfg.min_score, cfg.min_margin)


def run_on_image(cfg: Config, image_path: Path) -> int:
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print(f"image illisible : {image_path}", file=sys.stderr)
        return 2
    prompt = find_prompt(gray, cfg.min_side, cfg.max_side)
    if prompt is None:
        print("aucune case détectée")
        return 1
    match = build_recognizer(cfg).classify(prompt.glyph, prompt.mask)
    print(f"case {prompt.box} -> {match.label!r} (score {match.score:.2f})")
    return 0


def run_console(cfg: Config) -> int:
    from qte_bot.engine import Engine

    from qte_bot.io_win import real_io

    Engine(cfg, build_recognizer(cfg), CAPTURES_DIR, io=real_io()).run()
    return 0


LOG_FILE = PATHS.log
LOG_MAX_BYTES = 1_000_000
INSTANCE_NAME = "Local\\QteBot_AutoPrompt"
WINDOW_TITLE = "QTE Bot"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Appuie automatiquement sur la touche affichée dans la case QTE.")
    parser.add_argument("--config", type=Path, default=PATHS.config)
    parser.add_argument("--console", action="store_true", help="sans menu, messages dans la console")
    parser.add_argument("--label", action="store_true", help="étiqueter les lettres capturées pour en faire des modèles")
    parser.add_argument("--image", type=Path, help="tester la détection sur une capture d'écran au lieu de l'écran")
    args = parser.parse_args(argv)
    if args.config == PATHS.config:
        from qte_bot.storage import prepare
        done = prepare(PATHS)
        if done:
            print(done)
    cfg = load_config(args.config)
    if args.label:
        from qte_bot.labeler import label_glyphs
        return label_glyphs(GLYPHS_DIR, TEMPLATES_DIR, cfg.allowed_keys)
    if args.image:
        return run_on_image(cfg, args.image)
    return run_single(cfg, args)


def run_single(cfg: Config, args: argparse.Namespace) -> int:
    """Modes temps réel : refusés si une instance tourne déjà (sinon double appui sur chaque case)."""
    from qte_bot.single_instance import InstanceLock, focus_window

    lock = InstanceLock.acquire(INSTANCE_NAME)
    if lock is None:
        print("QTE Bot tourne déjà : fenêtre existante ramenée au premier plan.")
        focus_window(WINDOW_TITLE)
        return 0
    try:
        if args.console:
            return run_console(cfg)
        from qte_bot.gui import run_gui
        return run_gui(cfg, args.config, build_recognizer(cfg), PATHS)
    finally:
        lock.release()


def _setup_output() -> None:
    """Sans console (pythonw), stdout/stderr valent None : tout part dans qte_bot.log.

    Mode ajout (un 2e lancement refusé ne doit pas vider le log de l'instance en cours), rotation au-delà de 1 Mo.
    """
    if sys.stdout is None or sys.stderr is None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.replace(LOG_FILE.with_suffix(".old.log"))
        log = LOG_FILE.open("a", encoding="utf-8", buffering=1)
        log.write(f"--- lancement {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    else:
        sys.stdout.reconfigure(encoding="utf-8")


def _report_crash() -> None:
    """Plantage au démarrage sans console : trace dans le log + fenêtre d'alerte, jamais d'échec silencieux."""
    import traceback

    traceback.print_exc()
    try:
        import tkinter.messagebox as box
        box.showerror(WINDOW_TITLE, f"Le programme a planté.\nDétails : {LOG_FILE}")
    except Exception:  # pas d'affichage possible : la trace est déjà dans le log
        pass


def entry() -> None:
    """Point d'entrée commun (run.bat, QTE-Bot.exe) : sortie redirigée, plantage jamais silencieux."""
    _setup_output()
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        _report_crash()
        sys.exit(1)


if __name__ == "__main__":
    entry()
