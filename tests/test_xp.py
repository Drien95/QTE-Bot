import pytest

from qte_bot.xp import XpTracker


def session(xp, difficulty, verdicts, start, end):
    xp.start_session(difficulty, start)
    for v in verdicts:
        xp.record_case(v)
    return xp.end_session(end)


def test_full_session_earns_xp():
    xp = XpTracker()
    assert session(xp, 5, ["PRIS"] * 12, 0, 20) is True
    assert xp.total_xp == 85 and xp.by_difficulty[5].ok == 1


def test_failed_case_means_no_xp():
    xp = XpTracker()
    assert session(xp, 5, ["PRIS", "IGNORÉ ?"], 0, 5) is False
    assert xp.total_xp == 0 and xp.by_difficulty[5].failed == 1


def test_too_few_cases_is_a_failure():
    xp = XpTracker()
    assert session(xp, 3, ["PRIS"] * 5, 0, 5) is False  # Difficile = 8 QTE


def test_xp_per_hour_and_success_rate():
    xp = XpTracker()
    session(xp, 1, ["PRIS"] * 4, 0, 10)      # +15
    session(xp, 1, ["IGNORÉ ?"], 10, 20)
    assert xp.xp_per_hour(now=1800) == pytest.approx(30)  # 15 XP en 30 min
    assert xp.by_difficulty[1].rate == pytest.approx(0.5)


def test_end_without_start_is_ignored():
    assert XpTracker().end_session(5) is None
