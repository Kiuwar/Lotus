"""Componentes visuais estilo macOS para tkinter: botão-pílula e cartão.

Formas desenhadas com Pillow em 3× e reduzidas (bordas lisas). Ficam em
Canvas, então funcionam em qualquer sistema.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from conversor.ui.tema import Paleta, legivel, texto_sobre

SS = 3
FONTE = ("Segoe UI", 10) if sys.platform == "win32" else ("Helvetica", 12) if sys.platform == "darwin" else ("DejaVu Sans", 10)
FONTE_NEGRITO = (FONTE[0], FONTE[1], "bold")


def _hex(c: str) -> tuple[int, int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 255


def misturar(a: str, b: str, t: float) -> str:
    ca, cb = _hex(a), _hex(b)
    return "#" + "".join(f"{round(ca[i] + (cb[i] - ca[i]) * t):02X}" for i in range(3))


def retangulo_arredondado(w: int, h: int, raio: float, cor: str, fundo: str,
                          borda: str | None = None) -> Image.Image:
    """Retângulo arredondado liso sobre a cor de fundo do pai (sem transparência)."""
    w, h = max(w, 2), max(h, 2)
    img = Image.new("RGBA", (w * SS, h * SS), _hex(fundo))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), radius=raio * SS, fill=_hex(cor),
                        outline=_hex(borda) if borda else None, width=SS if borda else 0)
    return img.resize((w, h), Image.LANCZOS)


class BotaoPilula(tk.Canvas):
    """Botão arredondado. `primario` = cor de destaque cheia (como o azul do Mac).

    Aceita configure(state="disabled"/"normal") e ["state"], como um botão ttk.
    """

    def __init__(self, master, texto: str, command=None, pal: Paleta | None = None,
                 primario: bool = False, fundo: str | None = None, largura: int | None = None,
                 altura: int = 32, **kw):
        self.pal = pal
        self.texto, self.command, self.primario = texto, command, primario
        self.fundo = fundo or (pal.fundo if pal else "#F5F5F7")
        fonte = FONTE_NEGRITO if primario else FONTE
        self._fonte = fonte
        medir = tk.Label(master, text=texto, font=fonte)
        largura = largura or medir.winfo_reqwidth() + 28
        medir.destroy()
        super().__init__(master, width=largura, height=altura, highlightthickness=0, bd=0,
                         bg=self.fundo, cursor="hand2", **kw)
        self._estado_visual = "normal"
        self._fotos: dict = {}
        self.bind("<Enter>", lambda _e: self._visual("hover"))
        self.bind("<Leave>", lambda _e: self._visual("normal"))
        self.bind("<ButtonPress-1>", lambda _e: self._visual("pressionado"))
        self.bind("<ButtonRelease-1>", self._soltar)
        self._desenhar()

    def _cores(self) -> tuple[str, str, str | None]:
        pal = self.pal
        destaque = pal.destaque if pal else "#007AFF"
        sup = pal.superficie if pal else "#FFFFFF"
        if str(self.cget("state")) == "disabled":
            base = misturar(sup, self.fundo, 0.5)
            return base, misturar(pal.texto if pal else "#1D1D1F", base, 0.6), None
        if self.primario:
            cor = {"hover": misturar(destaque, "#000000", 0.08),
                   "pressionado": misturar(destaque, "#000000", 0.18)}.get(self._estado_visual, destaque)
            return cor, texto_sobre(cor), None
        cor = {"hover": misturar(sup, destaque, 0.08),
               "pressionado": misturar(sup, destaque, 0.18)}.get(self._estado_visual, sup)
        borda = misturar(sup, pal.texto if pal else "#1D1D1F", 0.15)
        return cor, pal.texto if pal else "#1D1D1F", borda

    def _desenhar(self) -> None:
        w, h = int(self["width"]), int(self["height"])
        cor, cor_txt, borda = self._cores()
        chave = (w, h, cor, borda)
        if chave not in self._fotos:
            self._fotos[chave] = ImageTk.PhotoImage(retangulo_arredondado(w, h, h / 2, cor, self.fundo, borda))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._fotos[chave])
        self.create_text(w / 2, h / 2, text=self.texto, fill=cor_txt, font=self._fonte)

    def _visual(self, estado: str) -> None:
        if str(self.cget("state")) != "disabled":
            self._estado_visual = estado
            self._desenhar()

    def _soltar(self, e) -> None:
        dentro = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self._visual("hover" if dentro else "normal")
        if dentro and self.command and str(self.cget("state")) != "disabled":
            self.command()

    def invoke(self) -> None:
        if self.command and str(self.cget("state")) != "disabled":
            self.command()

    def configure(self, cnf=None, **kw):
        texto = kw.pop("text", None)
        if texto is not None:
            self.texto = texto
        r = super().configure(cnf, **kw)
        if kw or texto is not None:
            self._desenhar()
        return r

    config = configure


class Cartao(tk.Canvas):
    """Área com cantos arredondados; ponha os widgets em `.interior`."""

    def __init__(self, master, pal: Paleta, fundo: str | None = None, raio: int = 12, pad: int = 12, **kw):
        self.pal, self.raio, self.pad = pal, raio, pad
        self.fundo = fundo or pal.fundo
        self._auto = True  # altura acompanha o conteúdo (até fixar_altura)
        super().__init__(master, highlightthickness=0, bd=0, bg=self.fundo, **kw)
        self.interior = tk.Frame(self, bg=pal.superficie)
        self._janela = self.create_window(pad, pad, anchor="nw", window=self.interior)
        self._foto = None
        self.bind("<Configure>", self._redimensionar)
        self.interior.bind("<Configure>", self._ajustar_altura)

    def _ajustar_altura(self, _e=None) -> None:
        if self._auto:  # o cartão cresce com o conteúdo
            self.configure(height=self.interior.winfo_reqheight() + 2 * self.pad)

    def fixar_altura(self) -> None:
        """O cartão passa a seguir a altura dada pelo layout (para áreas que esticam)."""
        self._auto = False

    def _redimensionar(self, e) -> None:
        w, h = e.width, e.height
        borda = misturar(self.pal.superficie, self.pal.texto, 0.10)
        self._foto = ImageTk.PhotoImage(retangulo_arredondado(w, h, self.raio, self.pal.superficie, self.fundo, borda))
        self.delete("fundo")
        self.create_image(0, 0, anchor="nw", image=self._foto, tags="fundo")
        self.tag_lower("fundo")
        self.itemconfigure(self._janela, width=max(1, w - 2 * self.pad))
        if not self._auto:
            self.itemconfigure(self._janela, height=max(1, h - 2 * self.pad))


def aplicar_estilo_ttk(root: tk.Misc, pal: Paleta) -> ttk.Style:
    """Cores do tema nos widgets ttk (lista, caixas de seleção, campos)."""
    st = ttk.Style(root)
    st.theme_use("clam")
    linha = misturar(pal.superficie, pal.texto, 0.12)
    sel = misturar(pal.superficie, pal.destaque, 0.25)
    st.configure(".", background=pal.superficie, foreground=pal.texto, font=FONTE,
                 bordercolor=linha, lightcolor=pal.superficie, darkcolor=pal.superficie,
                 troughcolor=misturar(pal.superficie, pal.texto, 0.06), focuscolor=pal.destaque)
    st.configure("TFrame", background=pal.superficie)
    st.configure("Fundo.TFrame", background=pal.fundo)
    st.configure("TLabel", background=pal.superficie, foreground=pal.texto)
    st.configure("Fundo.TLabel", background=pal.fundo, foreground=pal.texto_sec)
    st.configure("Secundario.TLabel", background=pal.superficie, foreground=pal.texto_sec)
    st.configure("Aviso.TLabel", background=pal.superficie, foreground=legivel("#FF3B30", pal.superficie))
    st.configure("TCheckbutton", background=pal.superficie, foreground=pal.texto)
    st.map("TCheckbutton", background=[("active", pal.superficie)],
           indicatorcolor=[("selected", pal.destaque), ("!selected", pal.superficie)])
    st.configure("TRadiobutton", background=pal.superficie, foreground=pal.texto)
    st.configure("Treeview", background=pal.superficie, fieldbackground=pal.superficie,
                 foreground=pal.texto, rowheight=26, borderwidth=0)
    st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # sem moldura própria
    st.map("Treeview", background=[("selected", sel)], foreground=[("selected", pal.texto)])
    st.configure("Treeview.Heading", background=pal.superficie, foreground=pal.texto_sec,
                 relief="flat", font=FONTE_NEGRITO)
    st.map("Treeview.Heading", background=[("active", pal.superficie)])
    st.configure("TCombobox", fieldbackground=pal.superficie, background=pal.superficie,
                 foreground=pal.texto, arrowcolor=pal.texto, padding=4)
    st.map("TCombobox", fieldbackground=[("readonly", pal.superficie)],
           foreground=[("readonly", pal.texto)], selectbackground=[("readonly", pal.superficie)],
           selectforeground=[("readonly", pal.texto)])
    st.configure("TEntry", fieldbackground=pal.superficie, foreground=pal.texto, padding=4)
    st.configure("Horizontal.TProgressbar", background=pal.destaque, troughcolor=linha,
                 bordercolor=linha, thickness=6)
    root.option_add("*TCombobox*Listbox.background", pal.superficie)
    root.option_add("*TCombobox*Listbox.foreground", pal.texto)
    root.option_add("*TCombobox*Listbox.selectBackground", pal.destaque)
    root.option_add("*TCombobox*Listbox.selectForeground", texto_sobre(pal.destaque))
    return st


def trazer_para_frente(janela: tk.Toplevel) -> None:
    """Abre a janela na frente das outras (ex.: aberta pelo ícone ao lado do
    relógio, cuja raiz é invisível). O `after` fica no `master` da janela, que
    continua existindo: fechar a janela antes não deixa comando apagado na fila
    do Tcl (regra 22)."""

    def soltar() -> None:
        try:
            if janela.winfo_exists():
                janela.attributes("-topmost", False)
        except tk.TclError:
            pass

    janela.lift()
    janela.attributes("-topmost", True)
    janela.focus_force()
    janela.master.after(400, soltar)
