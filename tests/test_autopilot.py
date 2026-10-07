import random

import pytest

from qte_bot.autopilot import Autopilot, AutoSettings, Observation, State

ROWS = [(744, 364 + 64 * i, 420, 56) for i in range(5)]  # 5 lignes du menu, Facile -> Extrême


class Fake:
    """Enregistre les actions demandées au lieu de toucher au clavier et à la souris."""

    def __init__(self):
        self.actions = []

    def press(self, key):
        self.actions.append(("press", key))

    def click(self, x, y):
        self.actions.append(("click", x, y))


def make(difficulties=(5,), max_sessions=20, pause=(5, 5)):
    fake = Fake()
    pilot = Autopilot(AutoSettings(set(difficulties), *pause, max_sessions), fake.press, fake.click, random.Random(0))
    return pilot, fake


def obs(now, menu=False, qte=False, katana=False, foreground=True):
    return Observation(now, foreground, ROWS if menu else [], qte, katana)


def run_session(pilot, t):
    """Une session complète à partir de IDLE : E, menu, clic, QTE, fin. Renvoie l'instant final."""
    pilot.step(obs(t))                       # appuie E
    pilot.step(obs(t + 0.3, menu=True))      # menu -> clic
    pilot.step(obs(t + 0.6, qte=True))       # entraînement lancé
    pilot.step(obs(t + 2.0, qte=True))
    pilot.step(obs(t + 5.0))                 # plus de QTE depuis > 2.5 s : session finie
    return t + 5.0


def test_full_cycle_presses_e_then_clicks_chosen_difficulty():
    pilot, fake = make(difficulties=(5,))
    run_session(pilot, 0.0)
    x, y, w, h = ROWS[4]
    assert fake.actions[0] == ("press", "e")
    assert fake.actions[1][0] == "click" and y <= fake.actions[1][2] <= y + h and x <= fake.actions[1][1] <= x + w
    assert pilot.state is State.COOLDOWN and pilot.sessions_done == 1


def test_random_difficulty_only_among_checked():
    pilot, fake = make(difficulties=(3, 5), pause=(0, 0))
    t = 0.0
    for _ in range(30):
        t = run_session(pilot, t) + 0.1
        pilot.step(obs(t))  # fin de pause -> IDLE
    rows_clicked = {next(i for i, (x, y, w, h) in enumerate(ROWS) if y <= a[2] <= y + h) + 1
                    for a in fake.actions if a[0] == "click"}
    assert rows_clicked == {3, 5}


def test_waits_for_cooldown_before_next_session():
    pilot, fake = make(pause=(10, 10))
    t = run_session(pilot, 0.0)
    pilot.step(obs(t + 5))
    assert pilot.state is State.COOLDOWN and fake.actions.count(("press", "e")) == 1
    pilot.step(obs(t + 10.1))
    pilot.step(obs(t + 10.2))
    assert fake.actions.count(("press", "e")) == 2


def test_stops_at_max_sessions():
    pilot, _ = make(max_sessions=1)
    run_session(pilot, 0.0)
    assert pilot.state is State.STOPPED and "limite" in pilot.reason


def test_katana_warning_stops_everything():
    pilot, fake = make()
    pilot.step(obs(0.0))
    pilot.step(obs(0.3, menu=True, katana=True))
    assert pilot.state is State.STOPPED and "katana" in pilot.reason
    assert ("click",) not in [a[:1] for a in fake.actions]


def test_never_acts_when_game_not_in_foreground():
    pilot, fake = make()
    for t in range(10):
        pilot.step(obs(float(t), menu=(t % 2 == 0), foreground=False))
    assert fake.actions == []


def test_stops_after_three_failed_menu_opens():
    pilot, fake = make()
    t = 0.0
    for _ in range(40):  # le menu ne s'ouvre jamais (pas dans le cercle)
        pilot.step(obs(t))
        t += 0.5
    assert pilot.state is State.STOPPED and "cercle" in pilot.reason
    assert fake.actions.count(("press", "e")) == 3


def test_successful_session_resets_failure_count():
    pilot, fake = make(pause=(0, 0))
    pilot.step(obs(0.0))      # E
    pilot.step(obs(2.5))      # timeout menu -> échec 1
    pilot.step(obs(5.0))      # E à nouveau
    t = run_session(pilot, 5.1)
    assert pilot.failures == 0 and pilot.sessions_done == 1


def test_menu_already_open_is_used_directly():
    pilot, fake = make()
    pilot.step(obs(0.0, menu=True))
    assert fake.actions[0][0] == "click" and pilot.state is State.WAIT_START


def test_training_started_by_hand_is_followed():
    pilot, fake = make()
    pilot.step(obs(0.0, qte=True))
    assert pilot.state is State.TRAINING and fake.actions == []


def test_rejects_invalid_settings():
    for bad in [AutoSettings(set(), 5, 10, 20), AutoSettings({6}, 5, 10, 20),
                AutoSettings({5}, 10, 5, 20), AutoSettings({5}, 5, 10, 0)]:
        with pytest.raises(ValueError):
            bad.validate()


def test_status_counts_down_whole_seconds_during_pause():
    pilot, _ = make(pause=(10, 10))
    t = run_session(pilot, 0.0)
    pilot.step(obs(t + 3.2))
    assert "7 s" in pilot.status


def test_status_says_when_game_is_not_in_front():
    pilot, _ = make()
    pilot.step(obs(0.0, foreground=False))
    assert "premier plan" in pilot.status


def test_pause_must_be_whole_seconds():
    with pytest.raises(ValueError):
        AutoSettings({5}, 2.5, 8, 20).validate()
