from qte_bot.hud import RESULT_MS, HudFeed, Phase


def test_live_box_is_drawn_until_next_frame_without_box():
    feed = HudFeed()
    feed.frame((10, 20, 80, 80), "z", Phase.WAITING, 0.4, now=1.0)
    marks = feed.marks(now=1.01)
    assert len(marks) == 1 and marks[0].phase is Phase.WAITING and marks[0].progress == 0.4
    feed.frame(None, None, Phase.SEEN, None, now=1.03)
    assert feed.marks(now=1.03) == []


def test_result_stays_visible_then_expires():
    feed = HudFeed()
    feed.result((10, 20, 80, 80), "z", "PRIS", now=2.0)
    assert [m.label for m in feed.marks(now=2.0 + RESULT_MS / 2000)] == ["Z  PRIS"]
    assert feed.marks(now=2.0 + RESULT_MS / 1000 + 0.01) == []


def test_results_are_bounded():
    feed = HudFeed()
    for i in range(50):
        feed.result((i, 0, 10, 10), "a", "PRIS", now=5.0)
    assert len(feed.marks(now=5.0)) <= 8


def test_fade_goes_from_1_to_0():
    feed = HudFeed()
    feed.result((0, 0, 10, 10), "a", "IGNORÉ ?", now=0.0)
    assert feed.marks(now=0.0)[0].fade == 1.0
    assert 0.0 < feed.marks(now=RESULT_MS / 1000 * 0.9)[0].fade < 0.2


def test_status_fields_have_safe_defaults():
    from qte_bot.hud import HudStatus

    s = HudStatus()
    assert not s.qte_on and not s.auto_on and s.progress is None and s.xp == 0


def test_thousands_formatting():
    from qte_bot.hud import thousands

    nbsp = " "  # espace fine insécable
    assert thousands(1785) == f"1{nbsp}785" and thousands(0) == "0" and thousands(12300.4) == f"12{nbsp}300"
