"""Chamadas à API do Windows usadas pelo atalho (somente Windows).

Todas as assinaturas (argtypes/restype) são declaradas: sem elas, o ctypes
trunca ponteiros e handles para 32 bits no Windows 64 bits.
Testado em tests/test_atalho_windows.py (roda no CI Windows).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t

WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_HOTKEY = 0x0312
WM_APP = 0x8000
LLMHF_INJECTED = 0x01
LLMHF_LOWER_IL_INJECTED = 0x02
GA_ROOT = 2

# Mensagens de mouse -> (botão, apertou?)
MOUSE_MSGS = {
    0x0201: ("esquerdo", True), 0x0202: ("esquerdo", False),
    0x0204: ("direito", True), 0x0205: ("direito", False),
    0x0207: ("meio", True), 0x0208: ("meio", False),
    0x020B: ("x", True), 0x020C: ("x", False),
}

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
# Tecla sem função usada como "máscara" (mesma técnica do AutoHotkey) para que
# soltar Alt/Win sozinho não abra o menu da janela nem o menu Iniciar.
VK_MASCARA = 0xE8

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
MOD_FLAGS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
KEYEVENTF_KEYUP = 0x0002

ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", w.POINT),
        ("mouseData", w.DWORD),
        ("flags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
        ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
        ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
user32.SetWindowsHookExW.restype = w.HHOOK
user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]
user32.UnhookWindowsHookEx.restype = w.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.GetMessageW.restype = w.BOOL
user32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
user32.PostThreadMessageW.restype = w.BOOL
user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
user32.RegisterHotKey.restype = w.BOOL
user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = w.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = w.SHORT
user32.WindowFromPoint.argtypes = [w.POINT]
user32.WindowFromPoint.restype = w.HWND
user32.GetAncestor.argtypes = [w.HWND, w.UINT]
user32.GetAncestor.restype = w.HWND
user32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = w.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
user32.GetCursorPos.restype = w.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = w.BOOL
user32.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = w.UINT

kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
kernel32.GetModuleHandleW.restype = w.HMODULE
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = w.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
kernel32.CreateMutexW.restype = w.HANDLE
kernel32.OpenMutexW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
kernel32.OpenMutexW.restype = w.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
kernel32.CreateEventW.restype = w.HANDLE
kernel32.OpenEventW.argtypes = [w.DWORD, w.BOOL, w.LPCWSTR]
kernel32.OpenEventW.restype = w.HANDLE
kernel32.SetEvent.argtypes = [w.HANDLE]
kernel32.SetEvent.restype = w.BOOL
kernel32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel32.WaitForSingleObject.restype = w.DWORD
kernel32.CloseHandle.argtypes = [w.HANDLE]
kernel32.CloseHandle.restype = w.BOOL


# ---------- utilidades ----------

def modificadores_pressionados() -> set[str]:
    def down(vk: int) -> bool:
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    mods = set()
    if down(VK_CONTROL):
        mods.add("ctrl")
    if down(VK_SHIFT):
        mods.add("shift")
    if down(VK_MENU):
        mods.add("alt")
    if down(VK_LWIN) or down(VK_RWIN):
        mods.add("win")
    return mods


def classe(hwnd) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def janela_raiz_no_ponto(x: int, y: int):
    h = user32.WindowFromPoint(w.POINT(x, y))
    return user32.GetAncestor(h, GA_ROOT) if h else None


def posicao_cursor() -> tuple[int, int]:
    p = w.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _tecla(vk: int, soltar: bool) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP if soltar else 0, time=0, dwExtraInfo=0)
    return i


def _mouse(flags: int) -> INPUT:
    i = INPUT(type=INPUT_MOUSE)
    i.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return i


def soltar_modificadores_e_clicar(mods: set[str]) -> int:
    """Solta (virtualmente) as teclas modificadoras e dá um clique esquerdo simples
    na posição atual do cursor, para o Explorer selecionar só o arquivo clicado."""
    seq: list[INPUT] = []
    if mods & {"alt", "win"}:
        seq += [_tecla(VK_MASCARA, False), _tecla(VK_MASCARA, True)]
    vks = {"ctrl": VK_CONTROL, "shift": VK_SHIFT, "alt": VK_MENU}
    for m in ("ctrl", "shift", "alt"):
        if m in mods:
            seq.append(_tecla(vks[m], True))
    if "win" in mods:
        seq += [_tecla(VK_LWIN, True), _tecla(VK_RWIN, True)]
    seq += [_mouse(MOUSEEVENTF_LEFTDOWN), _mouse(MOUSEEVENTF_LEFTUP)]
    arr = (INPUT * len(seq))(*seq)
    return user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


# ---------- instância única e pedido de parada ----------

NOME_MUTEX = "Local\\Lotus.Atalho"
NOME_EVENTO_PARAR = "Local\\Lotus.Atalho.Parar"


def criar_mutex_unico():
    """Retorna o handle se esta é a única instância; None se já há outra rodando."""
    h = kernel32.CreateMutexW(None, False, NOME_MUTEX)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(h)
        return None
    return h


def agente_rodando() -> bool:
    h = kernel32.OpenMutexW(SYNCHRONIZE, False, NOME_MUTEX)
    if h:
        kernel32.CloseHandle(h)
        return True
    return False


def criar_evento_parar():
    return kernel32.CreateEventW(None, True, False, NOME_EVENTO_PARAR)


def pedir_parada() -> bool:
    h = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, NOME_EVENTO_PARAR)
    if not h:
        return False
    try:
        return bool(kernel32.SetEvent(h))
    finally:
        kernel32.CloseHandle(h)


def evento_sinalizado(h) -> bool:
    return kernel32.WaitForSingleObject(h, 0) == WAIT_OBJECT_0
