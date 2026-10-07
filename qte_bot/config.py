"""Configuration typée, lue et validée à un seul endroit."""
from __future__ import annotations

import ctypes
import json
from dataclasses import dataclass
from pathlib import Path

from qte_bot.autopilot import AutoSettings

VK_FUNCTION_KEYS = {f"F{i}": 0x70 + i - 1 for i in range(1, 13)}
# Touches définies par leur POSITION physique (scancode) : le code virtuel dépend de la disposition
# du clavier, donc on le demande à Windows. 0x29 = touche à gauche du 1 (² en AZERTY, ` en QWERTY).
SCANCODE_KEYS = {"²": 0x29}
MAPVK_VSC_TO_VK = 1


@dataclass(frozen=True)
class Roi:
    """Zone de capture en fractions de l'écran principal (0..1)."""
    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Config:
    roi: Roi
    min_side: int
    max_side: int
    allowed_keys: str
    min_score: float
    min_margin: float
    confirm_frames: int
    release_frames: int
    hold_ms: int
    delay_min_ms: int  # délai d'appui tiré dans [min, max] depuis la 1re apparition de la case
    delay_max_ms: int
    fps: int
    hotkeys: dict[str, int]  # action -> virtual-key code
    game_process: str        # exécutable du jeu : aucune action si une autre fenêtre est active
    save_captures: bool      # image annotée de chaque case (diagnostic) ; désactivé par défaut
    auto: AutoSettings


def load_config(path: Path) -> Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = Config(
        roi=Roi(**raw["roi"]),
        min_side=int(raw["min_side"]),
        max_side=int(raw["max_side"]),
        allowed_keys=str(raw["allowed_keys"]).lower(),
        min_score=float(raw["min_score"]),
        min_margin=float(raw["min_margin"]),
        confirm_frames=int(raw["confirm_frames"]),
        release_frames=int(raw["release_frames"]),
        hold_ms=int(raw["hold_ms"]),
        delay_min_ms=int(raw.get("delay_min_ms", 0)),
        delay_max_ms=int(raw.get("delay_max_ms", 0)),
        fps=int(raw["fps"]),
        hotkeys={action: _vk(name) for action, name in raw["hotkeys"].items()},
        game_process=str(raw.get("game_process", "gmod.exe")).lower(),
        save_captures=bool(raw.get("save_captures", False)),
        auto=_auto(raw.get("auto", {})),
    )
    _validate(cfg)
    return cfg


def _auto(raw: dict) -> AutoSettings:
    return AutoSettings(
        difficulties={int(d) for d in raw.get("difficulties", [5])},
        pause_min_s=round(float(raw.get("pause_min_s", 5))),  # anciennes configs en décimal : arrondies
        pause_max_s=round(float(raw.get("pause_max_s", 15))),
        max_sessions=int(raw.get("max_sessions", 20)),
    )


def _vk(name: str) -> int:
    if name in VK_FUNCTION_KEYS:
        return VK_FUNCTION_KEYS[name]
    if name in SCANCODE_KEYS:
        vk = ctypes.windll.user32.MapVirtualKeyW(SCANCODE_KEYS[name], MAPVK_VSC_TO_VK)
        if vk == 0:
            raise ValueError(f"hotkey {name!r} : aucune touche correspondante sur ce clavier")
        return vk
    raise ValueError(f"hotkey inconnue : {name!r} (attendu F1..F12 ou {', '.join(SCANCODE_KEYS)})")


def _validate(cfg: Config) -> None:
    r = cfg.roi
    checks = {
        "roi hors écran": 0 <= r.left < 1 and 0 <= r.top < 1 and 0 < r.width <= 1 - r.left and 0 < r.height <= 1 - r.top,
        "0 < min_side <= max_side": 0 < cfg.min_side <= cfg.max_side,
        "allowed_keys doit contenir des lettres a-z": bool(cfg.allowed_keys) and cfg.allowed_keys.isalpha() and cfg.allowed_keys.isascii(),
        "min_score dans ]0, 1]": 0 < cfg.min_score <= 1,
        "confirm_frames et release_frames >= 1": cfg.confirm_frames >= 1 and cfg.release_frames >= 1,
        "hold_ms dans [1, 200]": 1 <= cfg.hold_ms <= 200,
        "0 <= delay_min_ms <= delay_max_ms <= 1000": 0 <= cfg.delay_min_ms <= cfg.delay_max_ms <= 1000,
        "fps dans [10, 500]": 10 <= cfg.fps <= 500,
        "hotkeys toggle/capture/quit requises": {"toggle", "capture", "quit"} <= cfg.hotkeys.keys(),
    }
    failed = [msg for msg, ok in checks.items() if not ok]
    try:
        cfg.auto.validate()
    except ValueError as exc:
        failed.append(f"auto : {exc}")
    if not cfg.game_process.endswith(".exe"):
        failed.append("game_process doit être un .exe")
    if failed:
        raise ValueError("config invalide : " + "; ".join(failed))


def save_timing(path: Path, delay_min_ms: int, delay_max_ms: int, hold_ms: int) -> None:
    """Réécrit seulement les réglages de timing, après validation, en gardant le reste du fichier."""
    _save(path, delay_min_ms=delay_min_ms, delay_max_ms=delay_max_ms, hold_ms=hold_ms)


def save_auto(path: Path, auto: AutoSettings) -> None:
    _save(path, auto={"difficulties": sorted(auto.difficulties), "pause_min_s": auto.pause_min_s,
                      "pause_max_s": auto.pause_max_s, "max_sessions": auto.max_sessions})


def _save(path: Path, **changes) -> None:
    """Écrit dans un fichier temporaire, le valide, puis remplace : jamais de config cassée sur disque."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(changes)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        load_config(tmp)  # lève ValueError si les valeurs sont invalides : on n'écrase rien
    except ValueError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
