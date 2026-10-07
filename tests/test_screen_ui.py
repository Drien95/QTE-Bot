from pathlib import Path

import cv2
import pytest

from qte_bot.screen_ui import find_difficulty_rows, katana_warning_visible

FIX = Path(__file__).parent / "fixtures"


def bgr(name):
    image = cv2.imread(str(FIX / f"{name}.png"))
    assert image is not None
    return image


def test_menu_has_five_rows_top_to_bottom():
    rows = find_difficulty_rows(bgr("menu"))
    assert len(rows) == 5
    ys = [r[1] for r in rows]
    assert ys == sorted(ys)
    # Ligne 5 (Extrême) vers y=620..676 sur la capture 1080p.
    x, y, w, h = rows[4]
    assert 600 <= y <= 640 and 40 <= h <= 70


@pytest.mark.parametrize("name", ["prompt_E", "full_E", "sample_w"])
def test_no_menu_when_closed(name):
    assert find_difficulty_rows(bgr(name)) == []


def test_katana_warning_detected():
    assert katana_warning_visible(cv2.cvtColor(bgr("menu"), cv2.COLOR_BGR2GRAY))


@pytest.mark.parametrize("name", ["prompt_E", "full_E"])
def test_katana_warning_absent(name):
    # full_E affiche un bandeau « Astuce » au même endroit : ne doit pas déclencher.
    assert not katana_warning_visible(cv2.cvtColor(bgr(name), cv2.COLOR_BGR2GRAY))
