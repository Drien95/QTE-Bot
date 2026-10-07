"""Méditation : les touches s'enchaînent dans une case qui ne disparaît jamais."""
import random

from qte_bot.chain import ChainDetector, ChainTracker

FRAME = 0.03


def run(tracker, labels):
    return [tracker.update(label, i * FRAME, visible=label is not None) for i, label in enumerate(labels)]


def make(delay=(0, 0)):
    tracker = ChainTracker(rng=random.Random(0))
    tracker.set_delay(*delay)
    return tracker


def test_each_new_letter_is_pressed_once():
    out = run(make(), ["a"] * 6 + ["z"] * 6 + ["e"] * 6)
    assert [k for k in out if k] == ["a", "z", "e"]


def test_stale_frame_never_repeats_the_old_letter_too_early():
    # Après l'appui sur « a », une ou deux images montrent encore « a » (retard de capture) : pas de 2e « a ».
    out = run(make(), ["a"] * 5 + ["a", "a"] + ["z"] * 6)
    assert out.count("a") == 1 and "z" in out


def test_repeated_letter_is_pressed_again_after_repeat_gap():
    # « a » puis « a » : la case montre « a » en continu ; on réappuie toutes les 250 ms.
    out = run(make(), ["a"] * 25)                      # 750 ms
    times = [round(i * FRAME, 2) for i, k in enumerate(out) if k]
    assert times[0] >= 0.1 and len(times) == 3 and all(b - a >= 0.25 for a, b in zip(times, times[1:]))


def test_new_letter_respects_min_gap():
    out = run(make(), ["a"] * 5 + ["z"] * 6)
    assert (out.index("z") - out.index("a")) * FRAME >= 0.08


def test_delay_applies_to_each_new_letter():
    out = run(make(delay=(100, 100)), ["a"] * 6 + ["z"] * 6)
    assert out.index("a") * FRAME >= 0.1
    assert (out.index("z") - 6) * FRAME >= 0.1


def test_box_gone_resets():
    tracker = make()
    seq = ["a"] * 5 + [None] * 4 + ["a"] * 5
    out = run(tracker, seq)
    assert out.count("a") == 2


def test_stuck_letter_is_capped():
    out = run(make(), ["a"] * 200)                     # 6 s sur la même lettre : le jeu ne prend plus
    assert out.count("a") <= 8


def test_detector_spots_letter_change_without_gap():
    d = ChainDetector()
    for i, label in enumerate(["a", "a", "z"]):
        d.update(True, label, i * FRAME)
    assert d.chain


def test_detector_ignores_combat_boxes_separated_by_gaps():
    d = ChainDetector()
    seq = [("a", True)] * 3 + [(None, False)] * 10 + [("z", True)] * 3
    for i, (label, visible) in enumerate(seq):
        d.update(visible, label, i * FRAME)
    assert not d.chain


def test_detector_keeps_meditation_across_sessions():
    d = ChainDetector()
    for i, label in enumerate(["a", "z"]):
        d.update(True, label, i * FRAME)
    d.update(False, None, 3.0)
    d.update(True, "q", 20.0)                           # session suivante, 1re lettre : toujours protégée
    assert d.chain


def test_detector_returns_to_combat_on_combat_signature():
    d = ChainDetector()
    for i, label in enumerate(["a", "z"]):
        d.update(True, label, i * FRAME)
    d.update(True, "q", 10.0)                           # nouvelle session (long calme) : on garde
    d.update(False, None, 10.5)
    d.update(True, "w", 11.2)                           # case disparue puis nouvelle case 0,7 s après : Combat
    assert not d.chain


def test_detector_tolerates_one_missed_frame():
    d = ChainDetector()
    seq = [("a", True), (None, False), ("z", True)]      # une image ratée au milieu : toujours la même case
    for i, (label, visible) in enumerate(seq):
        d.update(visible, label, i * FRAME)
    assert d.chain


def test_seed_prevents_immediate_repeat_after_switch():
    tracker = make()
    tracker.seed("a", 0.0)
    assert tracker.update("a", 0.05, visible=True) is None      # « a » vient d'être envoyé
    assert tracker.update("a", 0.30, visible=True) == "a"       # 250 ms après : lettre répétée


def test_first_press_waits_until_the_game_accepts_input_even_in_turbo():
    # Le jeu ignore un appui envoyé dès l'apparition (vu en Combat à ~60 ms, et en Méditation à +0 ms).
    out = run(make(delay=(0, 0)), ["a"] * 8)
    assert out.index("a") * FRAME >= 0.1


def test_single_transition_frame_is_never_pressed():
    # 21:58:26 : « 1 touche, case visible 0 ms » juste avant chaque échec -> image de transition.
    out = run(make(), ["a"] * 6 + ["w"] + ["z"] * 6)
    assert "w" not in out


def test_one_press_per_letter_when_game_moves_on():
    # Le jeu affiche la lettre suivante dès que la touche est prise : une seule touche par lettre.
    out = run(make(), ["a"] * 6 + ["z"] * 6 + ["e"] * 6)
    assert [k for k in out if k] == ["a", "z", "e"]
