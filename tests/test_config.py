import json
from pathlib import Path

import pytest

from qte_bot.config import load_config

ROOT_CONFIG = Path(__file__).resolve().parent.parent / "config.default.json"


def write(tmp_path: Path, **overrides) -> Path:
    raw = json.loads(ROOT_CONFIG.read_text(encoding="utf-8")) | overrides
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_shipped_config_is_valid():
    assert load_config(ROOT_CONFIG).allowed_keys.isalpha()


@pytest.mark.parametrize("overrides", [
    {"roi": {"left": 0.8, "top": 0, "width": 0.5, "height": 0.5}},
    {"min_side": 200, "max_side": 100},
    {"allowed_keys": "w;rm"},
    {"allowed_keys": ""},
    {"min_score": 0},
    {"hold_ms": 5000},
    {"fps": 0},
    {"delay_min_ms": 300, "delay_max_ms": 200},
    {"delay_min_ms": -1},
    {"delay_max_ms": 5000},
    {"auto": {"difficulties": [], "pause_min_s": 5, "pause_max_s": 15, "max_sessions": 20}},
    {"auto": {"difficulties": [7], "pause_min_s": 5, "pause_max_s": 15, "max_sessions": 20}},
    {"auto": {"difficulties": [5], "pause_min_s": 20, "pause_max_s": 15, "max_sessions": 20}},
    {"game_process": "gmod"},
    {"hotkeys": {"toggle": "F8", "capture": "F9", "quit": "ESC"}},
    {"hotkeys": {"toggle": "F8", "auto": "F8"}},  # même touche pour deux actions
])
def test_rejects_invalid_config(tmp_path, overrides):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, **overrides))


def test_square_key_resolves_to_key_left_of_1(tmp_path):
    hotkeys = {"toggle": "²", "capture": "F9", "quit": "F10"}
    vk = load_config(write(tmp_path, hotkeys=hotkeys)).hotkeys["toggle"]
    assert vk not in range(0x70, 0x7C)  # pas une touche F
    assert vk > 0


def test_save_timing_roundtrip_keeps_other_settings(tmp_path):
    from qte_bot.config import save_timing

    path = write(tmp_path)
    save_timing(path, 200, 500, 60)
    cfg = load_config(path)
    assert (cfg.delay_min_ms, cfg.delay_max_ms, cfg.hold_ms) == (200, 500, 60)
    assert cfg.allowed_keys == load_config(ROOT_CONFIG).allowed_keys


def test_save_timing_refuses_invalid_and_leaves_file_intact(tmp_path):
    from qte_bot.config import save_timing

    path = write(tmp_path)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        save_timing(path, 500, 200, 40)
    assert path.read_text(encoding="utf-8") == before


def test_save_auto_roundtrip(tmp_path):
    from qte_bot.autopilot import AutoSettings
    from qte_bot.config import save_auto

    path = write(tmp_path)
    save_auto(path, AutoSettings({3, 5}, 2, 8, 7))
    auto = load_config(path).auto
    assert (auto.difficulties, auto.pause_min_s, auto.pause_max_s, auto.max_sessions) == ({3, 5}, 2, 8, 7)


HOTKEYS = {"toggle": "²", "auto": "F7", "capture": "F9", "quit": "F10"}


def test_hotkeys_accept_letters_digits_and_vk_codes(tmp_path):
    cfg = load_config(write(tmp_path, hotkeys=HOTKEYS | {"auto": "P", "quit": "VK:123"}))
    assert cfg.hotkeys["auto"] == ord("P") and cfg.hotkeys["quit"] == 123


@pytest.mark.parametrize("bad", [
    HOTKEYS | {"auto": "Z"},          # Z est une lettre de QTE : le bot la tape lui-même
    HOTKEYS | {"auto": "E"},          # touche d'interaction de l'automatisation
    HOTKEYS | {"auto": "F10"},        # même touche pour deux actions
    HOTKEYS | {"auto": "VK:9999"},
])
def test_rejects_conflicting_or_invalid_hotkeys(tmp_path, bad):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, hotkeys=bad))


def test_save_hotkeys_roundtrip(tmp_path):
    from qte_bot.config import save_hotkeys

    path = write(tmp_path, hotkeys=HOTKEYS)
    save_hotkeys(path, HOTKEYS | {"auto": "VK:118"})
    assert load_config(path).hotkey_names["auto"] == "VK:118"
