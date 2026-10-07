import pytest

from qte_bot.xp import XpTracker


def session(xp, difficulty, verdicts, start, end):
    xp.start_session(difficulty, start)
    for v in verdicts:
        xp.record_case(v)
    return xp.end_session(end)


def test_full_session_earns_xp():
    xp = XpTracker()
    assert session(xp, 5, ["PRIS"] * 11, 0, 20) is True     # Extrême : 11 cases réellement affichées
    assert xp.total_xp == 85 and xp.by_difficulty[5].ok == 1


def test_failed_case_means_no_xp():
    xp = XpTracker()
    assert session(xp, 5, ["PRIS", "IGNORÉ ?"], 0, 5) is False
    assert xp.total_xp == 0 and xp.by_difficulty[5].failed == 1


def test_clean_session_is_a_success_whatever_the_count():
    # Le menu annonce 12 QTE en Extrême mais le jeu en montre 11 (21 sessions mesurées) :
    # on ne se fie plus au menu, une session sans case ratée est réussie.
    xp = XpTracker()
    assert session(xp, 3, ["PRIS"] * 7, 0, 5) is True


def test_session_without_any_case_is_not_a_success():
    assert session(XpTracker(), 5, [], 0, 3) is False


def test_xp_per_hour_and_success_rate():
    xp = XpTracker()
    session(xp, 1, ["PRIS"] * 4, 0, 10)      # +15
    session(xp, 1, ["IGNORÉ ?"], 10, 20)
    assert xp.xp_per_hour(now=1800) == pytest.approx(30)  # 15 XP en 30 min
    assert xp.by_difficulty[1].rate == pytest.approx(0.5)


def test_end_without_start_is_ignored():
    assert XpTracker().end_session(5) is None


def meditation(xp, presses, start, end, difficulty=5):
    xp.start_session(difficulty, start, activity="méditation")
    xp.record_chain(presses)
    return xp.end_session(end)


def test_meditation_cut_short_is_a_failure():
    # 21:58 : sessions normales ~18-23 touches, sessions annulées par un raté : 1 à 2 touches.
    xp = XpTracker()
    assert meditation(xp, 20, 0, 10) is True
    assert meditation(xp, 2, 10, 12) is False
    assert xp.total_xp == 85


def test_meditation_close_to_best_is_a_success():
    xp = XpTracker()
    meditation(xp, 22, 0, 10)
    assert meditation(xp, 18, 10, 20) is True             # 18/22 = 82 % >= 70 %


def test_meditation_best_is_per_difficulty():
    xp = XpTracker()
    meditation(xp, 22, 0, 10, difficulty=5)
    assert meditation(xp, 6, 10, 20, difficulty=1) is True  # 1re Méditation Facile : référence


def test_chain_presses_use_meditation_rule_even_if_title_misread():
    xp = XpTracker()
    xp.start_session(5, 0, activity="combat")             # titre mal lu
    xp.record_chain(20)
    assert xp.end_session(10) is True
