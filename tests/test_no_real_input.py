"""Le moteur ne doit jamais pouvoir agir sur le vrai jeu depuis un test ou un script."""
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from qte_bot.config import load_config
from qte_bot.engine import Engine
from qte_bot.game_io import GameIo
from qte_bot.main import ROOT, build_recognizer

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "config.json")


def test_engine_without_io_refuses_to_run(cfg):
    engine = Engine(cfg, build_recognizer(cfg), Path(tempfile.mkdtemp()))
    with pytest.raises(RuntimeError, match="io"):
        engine.run()


class FakeScreen:
    """Écran simulé : la capture plein écran avec la case « E » pendant `seconds` (temps réel), puis vide."""

    def __init__(self, seconds: float):
        self.box = cv2.cvtColor(cv2.imread(str(FIX / "full_E.png")), cv2.COLOR_BGR2BGRA)
        self.empty = np.zeros_like(self.box)
        self.until = None
        self.seconds = seconds
        self.region = {"left": 0, "top": 0, "width": self.box.shape[1], "height": self.box.shape[0]}

    def grab_bgra(self):
        now = time.perf_counter()
        self.until = self.until or now + self.seconds  # la case apparaît à la 1re capture
        return self.box if now < self.until else self.empty


class NoHotkeys:
    def __init__(self, _codes):
        pass

    def poll(self):
        return set()


def fake_io(presses, foreground="gmod.exe"):
    return GameIo(make_grabber=lambda _roi: FakeScreen(seconds=1.2), make_hotkeys=NoHotkeys,
                  press_key=lambda key, ms: presses.append(key), click_at=lambda x, y, fast: presses.append(("click", x, y)),
                  foreground_process=lambda: foreground)


def run_briefly(engine, seconds=1.5):
    worker = threading.Thread(target=engine.run, daemon=True)
    worker.start()
    time.sleep(seconds)
    engine.stop()
    worker.join(3)
    assert not worker.is_alive()


def test_engine_with_fake_io_presses_only_through_it(cfg):
    presses = []
    engine = Engine(cfg, build_recognizer(cfg), Path(tempfile.mkdtemp()), emit=lambda _l: None, io=fake_io(presses))
    run_briefly(engine)
    assert "e" in presses  # la case « E » de la capture a été lue et « appuyée »… dans la liste, pas dans le jeu


def test_engine_never_presses_when_game_not_in_front(cfg):
    presses = []
    engine = Engine(cfg, build_recognizer(cfg), Path(tempfile.mkdtemp()), emit=lambda _l: None,
                    io=fake_io(presses, foreground="explorer.exe"))
    run_briefly(engine)
    assert presses == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows uniquement")
def test_dry_run_blocks_sendinput_at_lowest_level(monkeypatch):
    from qte_bot import io_win

    sent = []

    class SpyUser32:
        def __getattr__(self, name):
            return getattr(io_win.ctypes.windll.user32, name)

        def SendInput(self, *args):  # noqa: N802 - nom de l'API Windows
            sent.append(args)
            return 1

    monkeypatch.setattr(io_win, "_user32", SpyUser32())
    io_win.press_key("e", 1)
    io_win.click_at(10, 10)
    assert sent == []


def test_unsure_letters_are_kept_for_learning(cfg):
    from qte_bot.episodes import Snapshot, Summary
    from qte_bot.detector import Box
    from qte_bot.recognizer import Match

    folder = Path(tempfile.mkdtemp())
    engine = Engine(cfg, build_recognizer(cfg), folder, emit=lambda _l: None)
    glyph = np.zeros((12, 10), np.uint8)
    snap = Snapshot(np.zeros((20, 20), np.uint8), Box(0, 0, 10, 10), glyph, glyph)
    engine._on_episode(Summary(18, 0, None, Match(None, 0.42, "s", 0.1), {"s": 18}, snap, 660, None, None,
                               unsure=(glyph, Match(None, 0.42, "s", 0.1))))
    saved = list((folder / "lettres").glob("*_s_0.42_*.png"))
    assert len(saved) == 1 and not list(folder.glob("*.png"))  # pas de capture d'écran, juste la lettre
