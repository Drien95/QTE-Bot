"""Une seule instance à la fois : deux moteurs appuieraient chacun sur la touche (double appui)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wt.HANDLE
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
_kernel32.CloseHandle.argtypes = [wt.HANDLE]


class InstanceLock:
    """Mutex nommé Windows : libéré automatiquement par le système si le programme plante."""

    def __init__(self, handle: int):
        self._handle = handle

    @classmethod
    def acquire(cls, name: str) -> InstanceLock | None:
        handle = _kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError(f"CreateMutexW a échoué (code {ctypes.get_last_error()})")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            return None
        return cls(handle)

    def release(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = 0


def focus_window(title: str) -> bool:
    """Ramène au premier plan la fenêtre déjà ouverte ; False si introuvable."""
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True
