"""Moldura própria da janela principal, estilo macOS (usada no Windows).

Barra de título com as "bolinhas" (fechar, minimizar, maximizar), título no
centro, botão "Ferramentas ▾" à direita, cantos arredondados e alça de
redimensionar. No Mac a moldura nativa já é assim, então lá não é usada; no
Windows o usuário pode voltar à moldura padrão em Aparência.

APIs do Windows (todas com argtypes/restype; regra 15):
- WS_EX_APPWINDOW: a janela sem moldura continua na barra de tarefas/Alt+Tab.
- SetWindowRgn + CreateRoundRectRgn: cantos arredondados no Windows 10.
- DwmSetWindowAttribute(DWMWA_WINDOW_CORNER_PREFERENCE): cantos lisos no 11.
- ShowWindow(SW_MINIMIZE): o Tk não minimiza janela sem moldura.
- SystemParametersInfoW(SPI_GETWORKAREA): maximizar sem cobrir a barra de tarefas.
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from conversor.logs import get_logger
from conversor.ui.tema import Paleta
from conversor.ui.widgets import FONTE, FONTE_NEGRITO, BotaoPilula, misturar

ALTURA_BARRA = 40
RAIO = 12
BOLINHAS = (("fechar", "#FF5F57", "×"), ("minimizar", "#FEBC2E", "–"), ("maximizar", "#28C840", "+"))

if sys.platform == "win32":
    from ctypes import wintypes as w

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    SW_MINIMIZE = 6
    SPI_GETWORKAREA = 0x0030
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2
    LONG_PTR = ctypes.c_ssize_t

    _user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = LONG_PTR
    _user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, LONG_PTR]
    _user32.SetWindowLongPtrW.restype = LONG_PTR
    _user32.SetWindowRgn.argtypes = [w.HWND, w.HRGN, w.BOOL]
    _user32.SetWindowRgn.restype = ctypes.c_int
    _user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = w.BOOL
    _user32.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, ctypes.c_void_p, w.UINT]
    _user32.SystemParametersInfoW.restype = w.BOOL
    _gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    _gdi32.CreateRoundRectRgn.restype = w.HRGN
    _gdi32.DeleteObject.argtypes = [w.HGDIOBJ]
    _gdi32.DeleteObject.restype = w.BOOL


def _bolinha(cor: str, simbolo: str | None, fundo: str, d: int = 13) -> Image.Image:
    ss = 4
    img = Image.new("RGBA", (d * ss, d * ss), fundo)
    dr = ImageDraw.Draw(img)
    dr.ellipse((0, 0, d * ss - 1, d * ss - 1), fill=cor, outline=misturar(cor, "#000000", 0.15), width=ss)
    if simbolo:
        c = d * ss / 2
        t = d * ss * 0.22
        tinta = misturar(cor, "#000000", 0.55)
        if simbolo == "×":
            dr.line((c - t, c - t, c + t, c + t), fill=tinta, width=ss + 1)
            dr.line((c - t, c + t, c + t, c - t), fill=tinta, width=ss + 1)
        else:
            dr.line((c - t, c, c + t, c), fill=tinta, width=ss + 1)
            if simbolo == "+":
                dr.line((c, c - t, c, c + t), fill=tinta, width=ss + 1)
    return img.resize((d, d), Image.LANCZOS)


class Moldura:
    def __init__(self, root: tk.Tk, pal: Paleta, titulo: str, propria: bool | None = None):
        self.root, self.pal, self.titulo = root, pal, titulo
        self.propria = (sys.platform == "win32") if propria is None else propria
        self.maximizada = False
        self._geo_normal = None
        self._arraste = None
        self._menu: tk.Menu | None = None
        self.hwnd: int | None = None
        self.log = get_logger()

        root.title(titulo)
        root.configure(bg=pal.fundo)
        if self.propria:
            root.overrideredirect(True)
            self._montar_barra()
        self.conteudo = tk.Frame(root, bg=pal.fundo)
        self.conteudo.pack(fill="both", expand=True)
        if self.propria:
            self._montar_alca()
            root.bind("<Configure>", self._ao_redimensionar, add="+")
            root.after(10, self._ajustes_windows)

    # ---------- barra de título ----------

    def _montar_barra(self) -> None:
        p = self.pal
        self.barra = tk.Canvas(self.root, height=ALTURA_BARRA, bg=p.fundo, highlightthickness=0, bd=0)
        self.barra.pack(fill="x", side="top")
        self._fotos = {}
        self.bolinhas = {}
        for i, (nome, cor, simb) in enumerate(BOLINHAS):
            self._fotos[nome] = (ImageTk.PhotoImage(_bolinha(cor, None, p.fundo)),
                                 ImageTk.PhotoImage(_bolinha(cor, simb, p.fundo)))
            x = 18 + i * 21
            item = self.barra.create_image(x, ALTURA_BARRA / 2, image=self._fotos[nome][0], tags=("bolinha", nome))
            self.bolinhas[nome] = item
            self.barra.tag_bind(nome, "<ButtonRelease-1>", lambda _e, n=nome: self.acao(n))
        # Como no macOS: os símbolos aparecem ao passar o mouse sobre o grupo de bolinhas.
        self.barra.tag_bind("bolinha", "<Enter>", lambda _e: self._simbolos(True))
        self.barra.tag_bind("bolinha", "<Leave>", lambda _e: self._simbolos(False))
        self._titulo_id = self.barra.create_text(0, ALTURA_BARRA / 2, text=self.titulo,
                                                 fill=p.texto_sec, font=FONTE_NEGRITO)
        self.btn_ferramentas = BotaoPilula(self.barra, "Ferramentas ▾", command=self._abrir_menu,
                                           pal=p, fundo=p.fundo, altura=26)
        self._btn_id = self.barra.create_window(0, ALTURA_BARRA / 2, window=self.btn_ferramentas, anchor="e")
        self.barra.bind("<Configure>", self._posicionar_barra)
        for alvo in (self.barra,):
            alvo.bind("<ButtonPress-1>", self._inicio_arraste)
            alvo.bind("<B1-Motion>", self._arrastar)
            alvo.bind("<Double-Button-1>", lambda _e: self.acao("maximizar"))

    def _posicionar_barra(self, e) -> None:
        self.barra.coords(self._titulo_id, e.width / 2, ALTURA_BARRA / 2)
        self.barra.coords(self._btn_id, e.width - 10, ALTURA_BARRA / 2)

    def _simbolos(self, mostrar: bool) -> None:
        for nome, item in self.bolinhas.items():
            self.barra.itemconfigure(item, image=self._fotos[nome][1 if mostrar else 0])

    def definir_menu(self, menu: tk.Menu) -> None:
        self._menu = menu

    def _abrir_menu(self) -> None:
        if self._menu is not None:
            b = self.btn_ferramentas
            self._menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)

    # ---------- ações ----------

    def acao(self, nome: str) -> None:
        if nome == "fechar":
            self.root.destroy()
        elif nome == "minimizar":
            self.minimizar()
        elif nome == "maximizar":
            self.alternar_maximizar()

    def minimizar(self) -> None:
        if sys.platform == "win32" and self.hwnd:
            _user32.ShowWindow(self.hwnd, SW_MINIMIZE)
        else:
            self.root.withdraw()  # reserva fora do Windows (sem moldura própria lá)

    def alternar_maximizar(self) -> None:
        if self.maximizada and self._geo_normal:
            self.root.geometry(self._geo_normal)
            self.maximizada = False
            return
        self._geo_normal = self.root.geometry()
        x, y, l, a = self.area_de_trabalho()
        self.root.geometry(f"{l}x{a}+{x}+{y}")
        self.maximizada = True

    def area_de_trabalho(self) -> tuple[int, int, int, int]:
        if sys.platform == "win32":
            r = w.RECT()
            if _user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    # ---------- arrastar e redimensionar ----------

    def _inicio_arraste(self, e) -> None:
        if self.barra.find_withtag("current") and "bolinha" in self.barra.gettags("current"):
            self._arraste = None
            return
        self._arraste = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _arrastar(self, e) -> None:
        if self._arraste and not self.maximizada:
            dx, dy = self._arraste
            self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _montar_alca(self) -> None:
        p = self.pal
        self.alca = tk.Canvas(self.root, width=16, height=16, bg=p.fundo, highlightthickness=0,
                              cursor="size_nw_se" if sys.platform == "win32" else "bottom_right_corner")
        for i in (4, 8, 12):
            self.alca.create_line(16, i, i, 16, fill=misturar(p.fundo, p.texto, 0.35))
        self.alca.place(relx=1.0, rely=1.0, anchor="se", x=-4, y=-4)
        self.alca.bind("<ButtonPress-1>", self._inicio_redim)
        self.alca.bind("<B1-Motion>", self._redimensionar)

    def _inicio_redim(self, e) -> None:
        self._redim = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _redimensionar(self, e) -> None:
        x0, y0, l0, a0 = self._redim
        mw, ma = self.root.minsize()
        largura, altura = max(mw, l0 + e.x_root - x0), max(ma, a0 + e.y_root - y0)
        self.root.geometry(f"{largura}x{altura}")
        self.maximizada = False

    # ---------- Windows: barra de tarefas e cantos ----------

    def _ajustes_windows(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self.hwnd = int(self.root.wm_frame(), 16)
            estilo = _user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
            _user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, (estilo & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
            # O Windows só reavalia a barra de tarefas ao reexibir a janela.
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
            try:
                dwm = ctypes.WinDLL("dwmapi")
                dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
                dwm.DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT
                pref = ctypes.c_int(DWMWCP_ROUND)
                dwm.DwmSetWindowAttribute(self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                          ctypes.byref(pref), ctypes.sizeof(pref))  # Win10: só ignora
            except OSError:
                pass
            self._aplicar_regiao()
        except Exception:
            self.log.exception("ajustes da moldura própria falharam")

    def _ao_redimensionar(self, e) -> None:
        if e.widget is self.root:
            self._aplicar_regiao()

    def _aplicar_regiao(self) -> None:
        if sys.platform != "win32" or not self.hwnd:
            return
        largura, altura = self.root.winfo_width(), self.root.winfo_height()
        if (largura, altura) == getattr(self, "_ultima_regiao", None):
            return
        self._ultima_regiao = (largura, altura)
        raio = 0 if self.maximizada else RAIO * 2
        rgn = _gdi32.CreateRoundRectRgn(0, 0, largura + 1, altura + 1, raio, raio)
        # Após sucesso, a região pertence ao Windows (não apagar); se falhar, apagamos.
        if rgn and not _user32.SetWindowRgn(self.hwnd, rgn, True):
            _gdi32.DeleteObject(rgn)


def centralizar(root: tk.Tk, largura: int, altura: int) -> None:
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - largura) // 2)
    y = max(0, (root.winfo_screenheight() - altura) // 3)
    root.geometry(f"{largura}x{altura}+{x}+{y}")


__all__ = ["Moldura", "centralizar", "FONTE"]
