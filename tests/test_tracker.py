import random

from qte_bot.tracker import MAX_PRESSES, PressTracker

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


def make_repress(after_ms=150, delay=(0, 0)):
    tracker = PressTracker(1, 3, rng=random.Random(0), insist_every_ms=after_ms)
    tracker.set_delay(*delay)
    return tracker


def test_insists_while_box_visible_every_150ms():
    # appui à 0 ; case toujours là -> nouvel appui toutes les 150 ms (images de 30 ms)
    out = feed(make_repress(), ["w"] * 12)
    times = [round(i * FRAME, 2) for i, k in enumerate(out) if k]
    assert times == [0.0, 0.15, 0.3]


def test_insist_is_capped():
    out = feed(make_repress(), ["w"] * 60)
    assert out.count("w") == MAX_PRESSES


def test_no_repress_when_box_vanishes():
    out = feed(make_repress(), ["w", "w", None, None, None, None])
    assert out.count("w") == 1


def test_repress_disabled():
    out = feed(make_repress(after_ms=None), ["w"] * 12)
    assert out.count("w") == 1


def unsure(tracker, guesses, score=0.42, start=0.0):
    """Case visible, lettre jamais lue avec certitude : seule la meilleure supposition est connue."""
    return [tracker.update(None, start + i * FRAME, visible=True, guess=g, guess_score=score)
            for i, g in enumerate(guesses)]


def test_fallback_presses_best_guess_when_never_sure():
    # Raté du 20:14:51 : S jamais reconnu (score 0.42), case visible 686 ms -> on tente « s » et on insiste.
    out = unsure(make_repress(delay=(200, 200)), ["s"] * 20)
    assert out[0:6] == [None] * 6           # pas avant le délai (200 ms)
    assert "s" in out and out.index("s") * FRAME >= 0.2
    assert out.count("s") >= 2              # puis insiste tant que la case reste


def test_fallback_needs_a_stable_guess():
    out = unsure(make_repress(), ["s", "q", "a", "s", "q", "a", "z", "x"])
    assert set(out) == {None}


def test_fallback_ignores_absurd_scores():
    out = unsure(make_repress(), ["s"] * 20, score=0.1)
    assert set(out) == {None}


def test_fallback_disabled_with_insist_off():
    out = unsure(make_repress(after_ms=None), ["s"] * 20)
    assert set(out) == {None}


def test_sure_letter_overrides_a_wrong_fallback():
    tracker = make_repress()
    unsure(tracker, ["q"] * 4)                          # tente « q »
    assert tracker.update("s", 4 * FRAME, visible=True) == "s"   # lecture certaine « s » : on corrige


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
