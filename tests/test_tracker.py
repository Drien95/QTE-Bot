import random

from qte_bot.tracker import PressTracker

FRAME = 0.03  # ~33 img/s


def feed(tracker, labels, start=0.0):
    """Une lettre (ou None) par image ; renvoie la touche pressée à chaque image."""
    return [tracker.update(label, start + i * FRAME) for i, label in enumerate(labels)]


def make(confirm=2, release=3, delay=(0, 0)):
    tracker = PressTracker(confirm, release, rng=random.Random(0))
    tracker.set_delay(*delay)
    return tracker


def test_presses_once_after_confirmation():
    assert feed(make(), ["w", "w", "w", "w"]) == [None, "w", None, None]


def test_single_frame_glitch_is_not_pressed():
    assert feed(make(), ["w", None, "a", None]) == [None, None, None, None]


def test_rearms_after_box_disappears():
    assert feed(make(1, 2), ["w", None, None, "w"]) == ["w", None, None, "w"]


def test_short_flicker_does_not_cause_double_press():
    assert feed(make(1, 3), ["w", None, "w"]) == ["w", None, None]


def test_new_letter_back_to_back_is_pressed():
    assert feed(make(1, 3), ["w", "w", "a"]) == ["w", None, "a"]


def test_delay_is_counted_from_first_sighting():
    # Délai fixe 100 ms : vue à t=0, appui à la 1re image où t >= 0.100 (image 4, t=0.12).
    out = feed(make(delay=(100, 100)), ["w"] * 6)
    assert out == [None, None, None, None, "w", None]


def test_no_press_if_box_vanishes_before_delay():
    out = feed(make(release=2, delay=(300, 300)), ["w", "w", "w", None, None, None])
    assert out == [None] * 6


def test_delay_survives_short_flicker():
    out = feed(make(release=3, delay=(100, 100)), ["w", "w", None, "w", "w", "w"])
    assert out == [None, None, None, None, "w", None]


def test_random_delay_stays_within_range():
    for seed in range(50):
        tracker = PressTracker(1, 3, rng=random.Random(seed))
        tracker.set_delay(200, 500)
        out = feed(tracker, ["q"] * 30)
        pressed_at = out.index("q") * FRAME
        assert 0.200 <= pressed_at < 0.500 + FRAME


def test_same_letter_after_other_letter_is_pressed():
    # Séquence du raté inexpliqué du 19:15:39 : q, z, puis q de nouveau, avec de courts trous.
    out = feed(make(release=4), ["q", "q", None, None, None, None, "z", "z", None, None, "q", "q", "q"])
    assert out.count("q") == 2 and out.count("z") == 1


def test_rejects_invalid_delay():
    tracker = make()
    for bad in [(-1, 10), (300, 200), (0, 5000)]:
        try:
            tracker.set_delay(*bad)
        except ValueError:
            continue
        raise AssertionError(f"délai {bad} accepté")


def test_progress_reports_delay_countdown():
    tracker = make(confirm=1, delay=(100, 100))
    tracker.update("w", 0.0)
    assert tracker.progress(0.05) == 0.5
    tracker.update("w", 0.1)  # appui
    assert tracker.progress(0.1) is None and tracker.pressed == "w"


def test_progress_is_none_without_pending_press():
    assert make().progress(0.0) is None


def make_repress(after_ms=150):
    tracker = PressTracker(1, 3, rng=random.Random(0), repress_after_ms=after_ms)
    tracker.set_delay(0, 0)
    return tracker


def test_repress_once_if_box_still_visible():
    # appui à t=0 ; case encore là à 0.15 s -> 2e appui ; jamais de 3e
    out = feed(make_repress(), ["w"] * 12)
    assert out[0] == "w" and out.count("w") == 2
    assert out.index("w", 1) * FRAME >= 0.150


def test_no_repress_when_box_vanishes():
    out = feed(make_repress(), ["w", "w", None, None, None, None])
    assert out.count("w") == 1


def test_repress_disabled():
    out = feed(make_repress(after_ms=None), ["w"] * 12)
    assert out.count("w") == 1


def test_repress_budget_resets_for_next_letter():
    out = feed(make_repress(), ["w"] * 7 + ["a"] * 7)
    assert out.count("w") == 2 and out.count("a") == 2


def test_unsure_frames_while_box_visible_do_not_reset():
    # Raté du 20:15:16 : S lu sur quelques images seulement, douteux (None) sur les autres, case toujours visible.
    tracker = make(confirm=2, release=3, delay=(200, 200))
    seq = ["s", None, None, None, None, "s", None, None, "s", None, "s"]
    out = [tracker.update(label, i * FRAME, visible=True) for i, label in enumerate(seq)]
    assert out.count("s") == 1


def test_box_really_gone_still_rearms():
    tracker = make(confirm=1, release=2)
    seq = [("w", True), (None, False), (None, False), ("w", True)]
    out = [tracker.update(label, i * FRAME, visible=vis) for i, (label, vis) in enumerate(seq)]
    assert out == ["w", None, None, "w"]
