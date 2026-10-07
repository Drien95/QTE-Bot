from pathlib import Path

import cv2
import numpy as np
import pytest

from qte_bot.detector import find_prompt
from qte_bot.recognizer import Recognizer, font_templates

FIXTURE = Path(__file__).parent / "fixtures" / "sample_w.png"


@pytest.fixture(scope="module")
def sample_gray() -> np.ndarray:
    image = cv2.imread(str(FIXTURE), cv2.IMREAD_GRAYSCALE)
    assert image is not None, f"fixture introuvable : {FIXTURE}"
    return image


@pytest.fixture(scope="module")
def recognizer() -> Recognizer:
    return Recognizer(font_templates("abcdefghijklmnopqrstuvwxyz"), min_score=0.4, min_margin=0.15)


def test_detects_the_prompt_box_in_sample(sample_gray):
    prompt = find_prompt(sample_gray, min_side=30, max_side=120)
    assert prompt is not None
    # La case de la capture est vers (190..243, 23..76).
    assert 180 <= prompt.box.x <= 200 and 15 <= prompt.box.y <= 35
    assert 40 <= prompt.box.w <= 65 and 40 <= prompt.box.h <= 65


def test_recognizes_w_in_sample(sample_gray, recognizer):
    prompt = find_prompt(sample_gray, min_side=30, max_side=120)
    assert prompt is not None
    assert recognizer.classify(prompt.glyph).label == "w"


def test_no_prompt_on_empty_dark_frame():
    frame = np.full((300, 300), 20, dtype=np.uint8)
    assert find_prompt(frame, min_side=30, max_side=120) is None


def test_no_prompt_for_box_without_glyph():
    frame = np.full((300, 300), 20, dtype=np.uint8)
    cv2.rectangle(frame, (100, 100), (152, 152), 170, 2)
    assert find_prompt(frame, min_side=30, max_side=120) is None


def test_rejects_non_square_rectangle():
    frame = np.full((300, 300), 20, dtype=np.uint8)
    cv2.rectangle(frame, (50, 100), (200, 140), 170, 2)
    cv2.putText(frame, "w", (115, 128), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 255, 2)
    assert find_prompt(frame, min_side=30, max_side=200) is None


def test_recognizer_refuses_low_confidence(recognizer):
    noise = np.random.default_rng(0).integers(0, 2, (24, 24), dtype=np.uint8) * 255
    assert recognizer.classify(noise).label is None


FULL_E = Path(__file__).parent / "fixtures" / "full_E.png"


def test_detects_thin_bordered_box_on_full_screen():
    # Écran 1080p complet : case à bord blanc de 1 px, coins arrondis, vers (522, 470), lettre E.
    gray = cv2.imread(str(FULL_E), cv2.IMREAD_GRAYSCALE)
    prompt = find_prompt(gray, min_side=30, max_side=160)
    assert prompt is not None
    assert 515 <= prompt.box.x <= 530 and 465 <= prompt.box.y <= 480


def test_round_button_and_character_are_not_boxes():
    # Seule la case doit sortir : ni le bouton rond « E S'entraîner », ni le personnage.
    gray = cv2.imread(str(FULL_E), cv2.IMREAD_GRAYSCALE)
    gray[460:560, 510:615] = 0  # on efface la vraie case
    assert find_prompt(gray, min_side=30, max_side=160) is None


def test_game_templates_read_the_full_screen_e():
    from qte_bot.config import load_config
    from qte_bot.main import ROOT, build_recognizer

    gray = cv2.imread(str(FULL_E), cv2.IMREAD_GRAYSCALE)
    prompt = find_prompt(gray, min_side=30, max_side=160)
    match = build_recognizer(load_config(ROOT / "config.json")).classify(prompt.glyph)
    assert match.label == "e"


GLYPHS = sorted((Path(__file__).parent / "fixtures" / "glyphs").glob("*.png"))


@pytest.mark.parametrize("path", GLYPHS, ids=lambda p: p.stem)
def test_game_templates_read_real_game_glyphs(path):
    # Lettres réellement capturées en jeu ; le nom du fichier commence par la bonne lettre.
    from qte_bot.config import load_config
    from qte_bot.detector import normalize_glyph
    from qte_bot.main import ROOT, build_recognizer

    recognizer = build_recognizer(load_config(ROOT / "config.json"))
    mask = np.where(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) >= 128, 255, 0).astype(np.uint8)
    match = recognizer.classify(normalize_glyph(mask), mask)
    assert match.label == path.stem[0], f"lu {match.guess} score {match.score:.2f} marge {match.margin:.2f}"
    assert match.score >= 0.85


def test_all_allowed_letters_have_game_templates():
    from qte_bot.config import load_config
    from qte_bot.main import ROOT, TEMPLATES_DIR
    from qte_bot.recognizer import load_templates

    cfg = load_config(ROOT / "config.json")
    assert {t.label for t in load_templates(TEMPLATES_DIR, cfg.allowed_keys)} == set(cfg.allowed_keys)
