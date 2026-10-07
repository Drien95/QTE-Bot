import sys

import pytest

from qte_bot.keys import key_label, spec_from_event


@pytest.mark.parametrize("keysym, keycode, char, expected", [
    ("F7", 118, "", "F7"),
    ("p", 80, "p", "P"),
    ("5", 53, "5", "5"),
    ("twosuperior", 222, "²", "²"),
    ("Insert", 45, "", "VK:45"),
])
def test_spec_from_event(keysym, keycode, char, expected):
    assert spec_from_event(keysym, keycode, char) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows uniquement")
def test_label_of_vk_is_readable():
    assert key_label("VK:45") not in ("", "VK:45")  # nom localisé, ex. « INSER »
    assert key_label("f7") == "F7"
