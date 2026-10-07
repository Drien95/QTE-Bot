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


def make(difficulties=(5,), max_sessions=20, pause=(5, 5), max_minutes=0, key="e"):
    fake = Fake()
    settings = AutoSettings(set(difficulties), *pause, max_sessions, max_minutes=max_minutes, interact_key=key)
    pilot = Autopilot(settings, fake.press, fake.click, random.Random(0))
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
                AutoSettings({5}, 10, 5, 20), AutoSettings({5}, 5, 10, 0),
                AutoSettings({5}, 5, 10, 20, max_minutes=-1), AutoSettings({5}, 5, 10, 20, interact_key="ee"),
                AutoSettings({5}, 5, 10, 20, interact_key="")]:
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


def test_custom_interact_key():
    pilot, fake = make(key="f")
    pilot.step(obs(0.0))
    assert fake.actions[0] == ("press", "f")


def test_stops_after_max_minutes_but_never_mid_session():
    pilot, _ = make(max_minutes=1, pause=(0, 0))
    pilot.step(obs(0.0))                      # démarrage du chrono + E
    pilot.step(obs(0.3, menu=True))
    pilot.step(obs(55.0, qte=True))           # session en cours au-delà de la minute...
    pilot.step(obs(61.0, qte=True))
    assert pilot.state is State.TRAINING      # ...on ne coupe pas au milieu
    pilot.step(obs(64.0))                     # fin de session
    assert pilot.state is State.STOPPED and "min" in pilot.reason


def test_session_callbacks_report_difficulty():
    events = []
    pilot, _ = make(difficulties=(4,))
    pilot.on_session = lambda kind, diff, now: events.append((kind, diff))
    run_session(pilot, 0.0)
    assert events == [("start", 4), ("end", 4)]


def test_manual_session_has_no_callbacks():
    events = []
    pilot, _ = make()
    pilot.on_session = lambda kind, diff, now: events.append(kind)
    pilot.step(obs(0.0, qte=True))
    pilot.step(obs(5.0))
    assert events == []


def start_session(pilot, t, difficulty_rows=None):
    pilot.step(obs(t))                   # E
    pilot.step(obs(t + 0.3, menu=True))  # clic
    pilot.step(obs(t + 0.6, qte=True))   # entraînement


def test_session_ends_right_after_last_expected_case():
    pilot, _ = make(difficulties=(5,), pause=(10, 10))
    start_session(pilot, 0.0)
    for i in range(11):                  # Extrême : 11 cases réellement affichées (le menu dit 12)
        pilot.case_done(True, 1.0 + i)
    pilot.step(obs(11.2))                # 0,2 s après la 11e case : pas d'attente de 2,5 s
    assert pilot.state is State.COOLDOWN and pilot.sessions_done == 1


def test_session_not_ended_before_last_case():
    pilot, _ = make(difficulties=(5,))
    start_session(pilot, 0.0)
    for i in range(10):
        pilot.step(obs(0.9 + i, qte=True))   # cases successives à l'écran
        pilot.case_done(True, 1.0 + i)
    pilot.step(obs(10.5))                     # 0,6 s après la 10e : on attend la 11e
    assert pilot.state is State.TRAINING


def test_failed_case_ends_session_after_short_grace():
    pilot, _ = make(difficulties=(5,), pause=(10, 10))
    start_session(pilot, 0.0)
    pilot.step(obs(1.0, qte=True))
    pilot.case_done(False, 1.2)
    pilot.step(obs(1.6))
    assert pilot.state is State.TRAINING          # pas encore : petite marge si le jeu continue
    pilot.step(obs(2.3))
    assert pilot.state is State.COOLDOWN


def test_new_case_after_failure_keeps_session_alive():
    pilot, _ = make(difficulties=(5,))
    start_session(pilot, 0.0)
    pilot.case_done(False, 1.0)
    pilot.step(obs(1.5, qte=True))               # le jeu a continué malgré l'échec
    pilot.step(obs(2.2, qte=True))
    assert pilot.state is State.TRAINING


def test_turbo_skips_pause_between_sessions():
    pilot, fake = make(difficulties=(5,), pause=(10, 10))
    pilot.turbo = True
    start_session(pilot, 0.0)
    for i in range(11):
        pilot.case_done(True, 1.0 + i)
    pilot.step(obs(11.1))              # fin de session
    pilot.step(obs(11.2))              # pas de pause : on relance tout de suite
    assert fake.actions[-1] == ("press", "e")


def test_turbo_retries_e_quickly():
    pilot, fake = make()
    pilot.turbo = True
    pilot.step(obs(0.0))               # E
    pilot.step(obs(0.8))               # menu absent après 0,7 s -> échec 1
    pilot.step(obs(1.4))               # nouvel essai 0,5 s plus tard
    assert fake.actions.count(("press", "e")) == 2


def clean_session(pilot, t, cases):
    start_session(pilot, t)
    for i in range(cases):
        pilot.step(obs(t + 1.0 + i * 0.9, qte=True))
        pilot.case_done(True, t + 1.1 + i * 0.9)
    end = t + 1.1 + cases * 0.9
    return end


def test_unknown_difficulty_falls_back_to_quiet_rule():
    pilot, _ = make(difficulties=(3,), pause=(0, 0))
    end = clean_session(pilot, 0.0, 7)
    pilot.step(obs(end + 0.3))
    assert pilot.state is State.TRAINING                 # nombre de cases pas encore connu
    pilot.step(obs(end + 2.6))
    assert pilot.sessions_done == 1


def test_case_count_is_learned_after_two_identical_clean_sessions():
    pilot, _ = make(difficulties=(3,), pause=(0, 0))
    t = 0.0
    for _ in range(2):                                   # deux sessions propres de 7 cases
        end = clean_session(pilot, t, 7)
        pilot.step(obs(end + 2.6))
        t = end + 3.0
    end = clean_session(pilot, t, 7)
    pilot.step(obs(end + 0.2))                           # 3e : fin immédiate, plus d'attente
    assert pilot.sessions_done == 3


def test_failed_session_does_not_teach_a_count():
    pilot, _ = make(difficulties=(3,), pause=(0, 0))
    t = 0.0
    for _ in range(2):
        start_session(pilot, t)
        pilot.case_done(True, t + 1.0)
        pilot.case_done(False, t + 2.0)
        pilot.step(obs(t + 3.1))
        t += 4.0
    assert pilot.expected_cases(3) is None
