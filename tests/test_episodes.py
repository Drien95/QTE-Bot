import numpy as np

from qte_bot.detector import Box, Prompt
from qte_bot.episodes import EpisodeLog
from qte_bot.recognizer import Match

FRAME = np.zeros((10, 10), np.uint8)
PROMPT = Prompt(Box(1, 1, 4, 4), np.zeros((2, 2), np.uint8), np.zeros((2, 2), np.uint8))


def run(events, release=2):
    ended = []
    log = EpisodeLog(release, ended.append)
    for i, (match, pressed) in enumerate(events):
        log.observe(i * 0.1, FRAME, PROMPT if match else None, match, pressed)
    return ended


def test_summary_after_box_disappears():
    ok = Match("w", 0.8, "w", 0.4)
    ended = run([(ok, None), (ok, "w"), (None, None), (None, None)])
    assert len(ended) == 1
    assert (ended[0].frames, ended[0].recognized, ended[0].pressed) == (2, 2, "w")


def test_missed_episode_keeps_best_guess():
    weak, better = Match(None, 0.3, "a", 0.05), Match(None, 0.38, "q", 0.1)
    ended = run([(weak, None), (better, None), (None, None), (None, None)])
    s = ended[0]
    assert s.pressed is None and s.recognized == 0
    assert s.best.guess == "q" and s.votes == {"a": 1, "q": 1}


def test_no_summary_while_box_still_visible():
    ok = Match("w", 0.8, "w", 0.4)
    assert run([(ok, None), (None, None), (ok, None)]) == []


def test_timings_show_how_fast_box_vanishes_after_press():
    ok = Match("w", 1.0, "w", 0.8)
    # vue à t=0.0, 0.1 (appui), 0.2, 0.3 puis disparue
    s = run([(ok, None), (ok, "w"), (ok, None), (ok, None), (None, None), (None, None)])[0]
    assert (s.visible_ms, s.press_after_ms, s.gone_after_press_ms) == (300, 100, 200)


def test_no_press_timings_when_not_pressed():
    weak = Match(None, 0.3, "a", 0.05)
    s = run([(weak, None), (None, None), (None, None)])[0]
    assert s.press_after_ms is None and s.gone_after_press_ms is None
