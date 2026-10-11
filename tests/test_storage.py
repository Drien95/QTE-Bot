"""Dossiers programme / données, premier lancement, purge des journaux."""
from pathlib import Path

import pytest

from qte_bot.paths import AppPaths, data_dir
from qte_bot.storage import human_size, logs_size, prepare, purge

DEFAULT = '{"from": "default"}'


def make(tmp_path: Path) -> AppPaths:
    app, data = tmp_path / "app", tmp_path / "data"
    app.mkdir()
    (app / "config.default.json").write_text(DEFAULT, encoding="utf-8")
    return AppPaths(app, data)


# ---------- où sont les données ----------
def test_installed_data_goes_to_localappdata_not_next_to_the_exe(tmp_path):
    assert data_dir(True, tmp_path / "prog", {"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "QTE-Bot"


def test_development_keeps_everything_in_the_project():
    assert data_dir(False, Path("C:/projet"), {}) == Path("C:/projet")


def test_env_override_wins(tmp_path):
    assert data_dir(True, tmp_path, {"QTE_BOT_DATA_DIR": str(tmp_path / "x"), "LOCALAPPDATA": "C:/"}) == tmp_path / "x"


def test_installed_without_localappdata_refuses_instead_of_guessing(tmp_path):
    with pytest.raises(RuntimeError):
        data_dir(True, tmp_path, {})


# ---------- premier lancement ----------
def test_first_launch_copies_default_settings(tmp_path):
    paths = make(tmp_path)
    assert "premier lancement" in prepare(paths)
    assert paths.config.read_text(encoding="utf-8") == DEFAULT


def test_existing_settings_are_never_overwritten(tmp_path):
    paths = make(tmp_path)
    paths.data.mkdir()
    paths.config.write_text('{"mine": 1}', encoding="utf-8")
    assert prepare(paths) is None
    assert paths.config.read_text(encoding="utf-8") == '{"mine": 1}'


def test_settings_of_version_1_0_are_migrated(tmp_path):
    paths = make(tmp_path)
    (paths.app / "config.json").write_text('{"old": 1}', encoding="utf-8")
    assert "ancienne version" in prepare(paths)
    assert paths.config.read_text(encoding="utf-8") == '{"old": 1}'


def test_missing_default_is_an_error_not_a_silent_empty_config(tmp_path):
    paths = make(tmp_path)
    (paths.app / "config.default.json").unlink()
    with pytest.raises(FileNotFoundError):
        prepare(paths)


# ---------- purge ----------
def fill(paths: AppPaths) -> None:
    paths.glyphs.mkdir(parents=True)
    paths.config.write_text("{}", encoding="utf-8")
    for p in (paths.event_log, paths.captures / "journal.old.txt", paths.captures / "a.png",
              paths.glyphs / "q_0.61.png", paths.data / "qte_bot.old.log", paths.log):
        p.write_bytes(b"x" * 100)


def test_purge_removes_logs_and_captures_but_keeps_settings(tmp_path):
    paths = make(tmp_path)
    fill(paths)
    assert logs_size(paths) == 600
    report = purge(paths)
    assert (report.files, report.freed, report.failed) == (5, 600, [])
    assert paths.config.exists() and paths.log.exists() and paths.log.stat().st_size == 0
    assert logs_size(paths) == 0


def test_purge_never_touches_other_files(tmp_path):
    paths = make(tmp_path)
    fill(paths)
    keep = [paths.data / "notes.md", paths.captures / "important.json", paths.app / "config.default.json"]
    for p in keep[:2]:
        p.write_text("garde", encoding="utf-8")
    purge(paths)
    assert all(p.exists() for p in keep)


def test_purge_truncates_log_held_open_by_the_program(tmp_path):
    paths = make(tmp_path)
    fill(paths)
    with paths.log.open("a", encoding="utf-8") as running:   # comme main._setup_output
        purge(paths)
        running.write("après purge\n")
    assert paths.log.read_text(encoding="utf-8") == "après purge\n"


def test_purge_on_empty_data_dir_is_a_no_op(tmp_path):
    paths = make(tmp_path)
    assert purge(paths).files == 0


def test_human_size():
    assert human_size(1_234_567) == "1,2 Mo" and human_size(2_500) == "2,5 Ko" and human_size(12) == "12 o"
