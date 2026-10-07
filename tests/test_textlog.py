from qte_bot.textlog import append_line


def test_rotates_when_too_big(tmp_path):
    path = tmp_path / "journal.txt"
    for i in range(200):
        append_line(path, f"ligne {i:03d} " + "x" * 50, max_bytes=2_000)
    assert path.stat().st_size <= 2_000 + 100
    assert (tmp_path / "journal.old.txt").exists()
    assert path.read_text(encoding="utf-8").splitlines()[-1].startswith("ligne 199")
