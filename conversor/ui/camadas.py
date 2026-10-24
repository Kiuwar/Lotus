"""Superfícies onde o painel é mostrado.

- Windows: janela em camadas (WS_EX_LAYERED + UpdateLayeredWindow) com
  transparência por pixel. Cantos/círculos lisos no Windows 10, e os pixels
  100% transparentes deixam o clique passar para o que está atrás.
- Outros sistemas (e reserva no Windows): imagem num Canvas comum.

Tudo da API do Windows declara argtypes/restype (regra 15 do CLAUDE.md);
tamanhos das estruturas são testados em tests/test_atalho_windows.py.
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk

from PIL import Image

from conversor.logs import get_logger

if sys.platform == "win32":
    from ctypes import wintypes as w

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TOPMOST = 0x00000008
    WS_EX_APPWINDOW = 0x00040000
    ULW_ALPHA = 0x02
    AC_SRC_OVER = 0x00
    AC_SRC_ALPHA = 0x01
    BI_RGB = 0
    DIB_RGB_COLORS = 0

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
            ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
            ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG),
            ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 1)]

    LONG_PTR = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = LONG_PTR
    user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, LONG_PTR]
    user32.SetWindowLongPtrW.restype = LONG_PTR
    user32.GetDC.argtypes = [w.HWND]
    user32.GetDC.restype = w.HDC
    user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.UpdateLayeredWindow.argtypes = [
        w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE), w.HDC,
        ctypes.POINTER(w.POINT), w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD,
    ]
    user32.UpdateLayeredWindow.restype = w.BOOL
    gdi32.CreateCompatibleDC.argtypes = [w.HDC]
    gdi32.CreateCompatibleDC.restype = w.HDC
    gdi32.CreateDIBSection.argtypes = [w.HDC, ctypes.POINTER(BITMAPINFO), w.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
    gdi32.CreateDIBSection.restype = w.HBITMAP
    gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]
    gdi32.SelectObject.restype = w.HGDIOBJ
    gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
    gdi32.DeleteObject.restype = w.BOOL
    gdi32.DeleteDC.argtypes = [w.HDC]
    gdi32.DeleteDC.restype = w.BOOL


def hwnd_de(top: tk.Misc) -> int:
    """HWND da janela de nível superior do Tk (a "moldura" que o Windows vê)."""
    return int(top.wm_frame(), 16)


def bgra_premultiplicado(img: Image.Image) -> bytes:
    """Formato exigido pelo UpdateLayeredWindow: BGRA com alfa pré-multiplicado."""
    return img.convert("RGBA").convert("RGBa").tobytes("raw", "BGRa")


class SuperficieCamadas:
    """Janela em camadas do Windows. Cada `mostrar` troca a imagem inteira."""

    def __init__(self, top: tk.Toplevel, x: int, y: int):
        self.top, self.x, self.y = top, x, y
        top.update_idletasks()
        self.hwnd = hwnd_de(top)
        estilo = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        novo = (estilo | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
        if not user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, novo) and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())

    def mostrar(self, img: Image.Image) -> None:
        largura, altura = img.size
        tela = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(tela)
        bits = ctypes.c_void_p()
        bmi = BITMAPINFO()
        bmi.bmiHeader = BITMAPINFOHEADER(
            biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=largura,
            biHeight=-altura,  # negativo = linhas de cima para baixo
            biPlanes=1, biBitCount=32, biCompression=BI_RGB,
        )
        hbmp = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        try:
            if not hbmp or not bits.value:
                raise ctypes.WinError(ctypes.get_last_error())
            dados = bgra_premultiplicado(img)
            ctypes.memmove(bits.value, dados, len(dados))
            antigo = gdi32.SelectObject(mem, hbmp)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            ok = user32.UpdateLayeredWindow(
                self.hwnd, tela, ctypes.byref(w.POINT(self.x, self.y)), ctypes.byref(w.SIZE(largura, altura)),
                mem, ctypes.byref(w.POINT(0, 0)), 0, ctypes.byref(blend), ULW_ALPHA,
            )
            gdi32.SelectObject(mem, antigo)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if hbmp:
                gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, tela)


class SuperficieTk:
    """Reserva: imagem num Canvas (sem transparência real nos cantos)."""

    def __init__(self, top: tk.Toplevel, x: int, y: int, largura: int, altura: int, fundo: str):
        from PIL import ImageTk

        self._ImageTk = ImageTk
        self.fundo = fundo
        top.geometry(f"{largura}x{altura}+{x}+{y}")
        self.canvas = tk.Canvas(top, width=largura, height=altura, highlightthickness=0, bd=0, bg=fundo)
        self.canvas.pack()
        self._foto = None
        self._id = None

    def mostrar(self, img: Image.Image) -> None:
        base = Image.new("RGBA", img.size, self.fundo)
        self._foto = self._ImageTk.PhotoImage(Image.alpha_composite(base, img))
        if self._id is None:
            self._id = self.canvas.create_image(0, 0, anchor="nw", image=self._foto)
        else:
            self.canvas.itemconfigure(self._id, image=self._foto)


def criar(top: tk.Toplevel, x: int, y: int, largura: int, altura: int, fundo: str):
    """Janela em camadas no Windows; se algo falhar, a reserva (e registra no log)."""
    if sys.platform == "win32":
        try:
            top.geometry(f"{largura}x{altura}+{x}+{y}")
            return SuperficieCamadas(top, x, y)
        except Exception:
            get_logger().exception("janela em camadas indisponível; usando a reserva")
    return SuperficieTk(top, x, y, largura, altura, fundo)
