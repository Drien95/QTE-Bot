"""Entrées/sorties Windows : capture d'écran, envoi de touches, raccourcis globaux."""
from __future__ import annotations

import ctypes
import os
import time

import cv2
import ctypes.wintypes as wt

import mss
import numpy as np

from qte_bot.config import Roi

_user32 = ctypes.windll.user32
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    # L'union INPUT fait la taille de son plus gros membre (MOUSEINPUT) : padding pour que cbSize soit juste.
    _fields_ = [("type", wt.DWORD), ("ki", _KEYBDINPUT), ("_pad", ctypes.c_ubyte * 8)]


def capture_region(roi: Roi, sct: mss.base.MSSBase | None = None) -> dict[str, int]:
    """Rectangle écran (px physiques) capturé : la fraction `roi` de l'écran principal."""
    owned = sct is None
    sct = sct or mss.mss()
    try:
        mon = sct.monitors[1]
    finally:
        if owned:
            sct.close()
    return {
        "left": mon["left"] + int(mon["width"] * roi.left),
        "top": mon["top"] + int(mon["height"] * roi.top),
        "width": int(mon["width"] * roi.width),
        "height": int(mon["height"] * roi.height),
    }


class ScreenGrabber:
    """Capture une zone fixe de l'écran principal en niveaux de gris."""

    def __init__(self, roi: Roi):
        self._sct = mss.mss()
        self.region = capture_region(roi, self._sct)

    def grab_bgra(self) -> np.ndarray:
        return np.asarray(self._sct.grab(self.region))

    def grab_gray(self) -> np.ndarray:
        # cv2 (SIMD) : ~0.1 ms contre ~7 ms pour le calcul équivalent en numpy flottant.
        return cv2.cvtColor(self.grab_bgra(), cv2.COLOR_BGRA2GRAY)


def scancode_for(char: str) -> int:
    """Scancode de la touche qui produit `char` sur la disposition ACTIVE (AZERTY : 'a' -> 0x10, pas 0x1E)."""
    vk = _user32.VkKeyScanW(ord(char))
    if vk == -1:
        raise ValueError(f"aucune touche ne produit {char!r} sur ce clavier")
    scancode = _user32.MapVirtualKeyW(vk & 0xFF, MAPVK_VK_TO_VSC)
    if scancode == 0:
        raise ValueError(f"pas de scancode pour {char!r}")
    return scancode


def press_key(key: str, hold_ms: int) -> None:
    """Appui physique simulé via SendInput en scancode (lu aussi par les jeux DirectInput/Raw Input)."""
    scancode = scancode_for(key)
    _send(scancode, KEYEVENTF_SCANCODE)
    try:
        time.sleep(hold_ms / 1000)
    finally:  # quoi qu'il arrive (erreur, arrêt), la touche ne doit jamais rester enfoncée dans le jeu
        _send(scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP)


DRY_RUN_ENV = "QTE_BOT_DRY_RUN"


def dry_run() -> bool:
    """QTE_BOT_DRY_RUN=1 (posé par les tests) : aucune touche ni clic ne sort, quoi que fasse l'appelant."""
    return os.environ.get(DRY_RUN_ENV) == "1"


def _send(scancode: int, flags: int) -> None:
    if dry_run():
        return
    event = _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(wVk=0, wScan=scancode, dwFlags=flags))
    if _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
        raise OSError(f"SendInput refusé (jeu lancé en administrateur ?) code {ctypes.GetLastError()}")


class Hotkeys:
    """Détecte les fronts montants des touches F* sans hook clavier global."""

    def __init__(self, bindings: dict[str, int]):
        self._bindings = bindings
        self._down = {action: False for action in bindings}

    def poll(self) -> set[str]:
        fired = set()
        for action, vk in self._bindings.items():
            is_down = bool(_user32.GetAsyncKeyState(vk) & 0x8000)
            if is_down and not self._down[action]:
                fired.add(action)
            self._down[action] = is_down
        return fired


# --- souris ---
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE = 0x0001, 0x8000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
SM_CXSCREEN, SM_CYSCREEN = 0, 1
CLICK_HOLD_S = 0.12
CLICK_SETTLE_S = 0.15  # le jeu relit la position du curseur à chaque image : on le laisse « voir » le curseur arriver


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSE_INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("mi", _MOUSEINPUT)]


def click_at(x: int, y: int) -> None:
    """Clic gauche à (x, y) en pixels de l'écran principal : déplacement absolu puis appui/relâche."""
    w, h = _user32.GetSystemMetrics(SM_CXSCREEN), _user32.GetSystemMetrics(SM_CYSCREEN)
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"clic hors de l'écran principal : ({x}, {y}) pour {w}x{h}")
    def norm(px: int, py: int) -> tuple[int, int]:  # coordonnées normalisées 0..65535
        return round(px * 65535 / (w - 1)), round(py * 65535 / (h - 1))

    # Approche en deux temps (à côté puis dessus) : le jeu reçoit un vrai mouvement au-dessus de la cible.
    _send_mouse(*norm(max(0, x - 6), max(0, y - 3)), MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(0.04)
    nx, ny = norm(x, y)
    _send_mouse(nx, ny, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    time.sleep(CLICK_SETTLE_S)
    _send_mouse(nx, ny, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE)
    try:
        time.sleep(CLICK_HOLD_S)
    finally:  # comme pour les touches : le bouton ne doit jamais rester enfoncé
        _send_mouse(nx, ny, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE)


def _send_mouse(nx: int, ny: int, flags: int) -> None:
    if dry_run():
        return
    event = _MOUSE_INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(dx=nx, dy=ny, dwFlags=flags))
    if _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_INPUT)) != 1:
        raise OSError(f"SendInput souris refusé, code {ctypes.GetLastError()}")


# --- fenêtre active ---
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_kernel32 = ctypes.windll.kernel32


def foreground_process() -> str:
    """Nom de l'exécutable de la fenêtre au premier plan (en minuscules), '' si inconnu."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(260), wt.DWORD(260)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        _kernel32.CloseHandle(handle)


def real_io():
    """Les vrais accès système. À n'utiliser que dans les points d'entrée (menu, --console)."""
    from qte_bot.game_io import GameIo

    return GameIo(make_grabber=ScreenGrabber, make_hotkeys=Hotkeys, press_key=press_key,
                  click_at=click_at, foreground_process=foreground_process)
