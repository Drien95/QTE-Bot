"""Rythme de réinsistance : la touche doit rester RELÂCHÉE assez longtemps entre deux appuis.

08/10 20:06 (Turbo) : appui tenu 45 ms puis réappui 50 ms après le début -> touche relâchée ~5 ms seulement.
Le jeu ne voit pas ce relâchement (il lit l'état des touches par tick) : pour lui la touche reste enfoncée,
aucun nouvel appui n'est compté, et la case expire (« IGNORÉ ? » à +500 ms, case partie ~250 ms après).
"""
from qte_bot.engine import BOX_LIFETIME_MS, MIN_RELEASE_MS, insist_plan


def test_turbo_leaves_the_key_released_long_enough():
    every_ms, _ = insist_plan(hold_ms=45, turbo=True)
    assert every_ms - 45 >= MIN_RELEASE_MS


def test_turbo_keeps_insisting_for_the_whole_box_lifetime():
    every_ms, max_presses = insist_plan(hold_ms=45, turbo=True)
    assert (max_presses - 1) * every_ms >= BOX_LIFETIME_MS - every_ms


def test_long_hold_never_eats_the_release():
    for turbo in (True, False):
        every_ms, _ = insist_plan(hold_ms=120, turbo=turbo)
        assert every_ms - 120 >= MIN_RELEASE_MS


def test_normal_mode_rhythm_unchanged_with_default_hold():
    assert insist_plan(hold_ms=45, turbo=False)[0] == 150
