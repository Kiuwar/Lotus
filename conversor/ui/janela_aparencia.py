"""Janela "Aparência": personaliza o painel e a janela, com prévia ao vivo."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk

from conversor.ui import grupos, radial, render, tema

NOMES_MODO = {"auto": "Seguir o sistema", "claro": "Claro", "escuro": "Escuro"}
NOMES_FORMA = {"radial": "Radial (em volta do cursor)", "cartao": "Cartão (lista)"}
NOMES_TAMANHO = {"P": "Pequeno", "M": "Médio", "G": "Grande"}
EXEMPLO = ["png", "jpg", "pdf", "docx", "txt", "xlsx"]


class JanelaAparencia(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title("Lotus — aparência")
        self.resizable(False, False)
        self.atual = tema.carregar()
        self.cores: dict[str, str | None] = {"destaque": self.atual.destaque, "fundo": self.atual.fundo}
        self.cores_grupo: dict[str, str] = dict(self.atual.cores_grupo)

        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        esq = ttk.Frame(f)
        esq.grid(row=0, column=0, sticky="n")

        def linha(r, rotulo):
            ttk.Label(esq, text=rotulo).grid(row=r, column=0, sticky="w", pady=4)

        self.v_tema = tk.StringVar(value=self.atual.tema)
        linha(0, "Tema")
        cb = ttk.Combobox(esq, textvariable=self.v_tema, values=list(tema.PRESETS), state="readonly", width=22)
        cb.grid(row=0, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        self.v_modo = tk.StringVar(value=self.atual.modo)
        linha(1, "Claro/escuro")
        fm = ttk.Frame(esq)
        fm.grid(row=1, column=1, sticky="w")
        for m, n in NOMES_MODO.items():
            ttk.Radiobutton(fm, text=n, value=m, variable=self.v_modo, command=self.atualizar).pack(side="left", padx=(0, 6))

        self.v_forma = tk.StringVar(value=self.atual.forma)
        linha(2, "Forma do painel")
        ff = ttk.Frame(esq)
        ff.grid(row=2, column=1, sticky="w")
        for m, n in NOMES_FORMA.items():
            ttk.Radiobutton(ff, text=n, value=m, variable=self.v_forma, command=self.atualizar).pack(anchor="w")

        self.v_tamanho = tk.StringVar(value=self.atual.tamanho)
        linha(3, "Tamanho")
        ft = ttk.Frame(esq)
        ft.grid(row=3, column=1, sticky="w")
        for m, n in NOMES_TAMANHO.items():
            ttk.Radiobutton(ft, text=n, value=m, variable=self.v_tamanho, command=self.atualizar).pack(side="left", padx=(0, 6))

        self.v_opac = tk.IntVar(value=round(self.atual.opacidade * 100))
        linha(4, "Opacidade do fundo")
        fo = ttk.Frame(esq)
        fo.grid(row=4, column=1, sticky="w")
        ttk.Scale(fo, from_=60, to=100, variable=self.v_opac, length=170,
                  command=lambda _v: self.atualizar()).pack(side="left")
        self.l_opac = ttk.Label(fo, width=5)
        self.l_opac.pack(side="left", padx=6)

        linha(5, "Cores")
        fc = ttk.Frame(esq)
        fc.grid(row=5, column=1, sticky="w")
        self.amostras: dict[str, tk.Label] = {}
        alvos = [("destaque", "Destaque"), ("fundo", "Fundo"), *[(g, g) for g in tema.GRUPOS]]
        for i, (chave, nome) in enumerate(alvos):
            amostra = tk.Label(fc, width=3, relief="solid", bd=1, cursor="hand2")
            amostra.grid(row=i, column=0, pady=2, sticky="w")
            amostra.bind("<Button-1>", lambda _e, c=chave: self.escolher_cor(c))
            ttk.Label(fc, text=nome).grid(row=i, column=1, sticky="w", padx=6)
            ttk.Button(fc, text="Padrão", width=7,
                       command=lambda c=chave: self.definir_cor(c, None)).grid(row=i, column=2, padx=2)
            self.amostras[chave] = amostra

        self.v_moldura = tk.BooleanVar(value=self.atual.moldura_windows)
        if sys.platform == "win32":
            ttk.Checkbutton(esq, text="Usar a moldura padrão do Windows na janela principal",
                            variable=self.v_moldura).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        dir_ = ttk.Frame(f, padding=(16, 0, 0, 0))
        dir_.grid(row=0, column=1, sticky="n")
        ttk.Label(dir_, text="Prévia").pack(anchor="w")
        self.previa = tk.Label(dir_, bd=0)
        self.previa.pack()

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="Restaurar padrão", command=self.padrao).pack(side="left", padx=4)
        ttk.Button(bar, text="Salvar", command=self.salvar).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.atualizar()

    # ---------- estado ----------

    def aparencia(self) -> tema.Aparencia:
        return replace(
            self.atual,
            tema=self.v_tema.get(), modo=self.v_modo.get(), forma=self.v_forma.get(),
            tamanho=self.v_tamanho.get(), opacidade=round(self.v_opac.get()) / 100,
            destaque=self.cores["destaque"], fundo=self.cores["fundo"],
            cores_grupo={g: c for g, c in self.cores_grupo.items() if c},
            moldura_windows=self.v_moldura.get(),
        )

    def definir_cor(self, chave: str, cor: str | None) -> None:
        if chave in ("destaque", "fundo"):
            self.cores[chave] = cor
        elif cor:
            self.cores_grupo[chave] = cor
        else:
            self.cores_grupo.pop(chave, None)
        self.atualizar()

    def escolher_cor(self, chave: str) -> None:
        pal = tema.paleta(self.aparencia())
        inicial = pal.destaque if chave == "destaque" else pal.fundo if chave == "fundo" else pal.grupos[chave]
        _, cor = colorchooser.askcolor(color=inicial, parent=self, title=f"Cor: {chave}")
        if cor:
            self.definir_cor(chave, cor.upper())

    def padrao(self) -> None:
        self.atual = tema.PADRAO
        self.cores = {"destaque": None, "fundo": None}
        self.cores_grupo = {}
        self.v_tema.set(tema.PADRAO.tema)
        self.v_modo.set(tema.PADRAO.modo)
        self.v_forma.set(tema.PADRAO.forma)
        self.v_tamanho.set(tema.PADRAO.tamanho)
        self.v_opac.set(round(tema.PADRAO.opacidade * 100))
        self.v_moldura.set(False)
        self.atualizar()

    def imagem_previa(self) -> Image.Image:
        a = self.aparencia()
        pal = tema.paleta(a)
        lay = radial.montar(grupos.agrupar(EXEMPLO), a.forma, tema.TAMANHOS[a.tamanho] * 0.85)
        img = render.desenhar(lay, pal, "exemplo.pdf", "pdf", a.opacidade, hover=lay.itens[0].fmt)
        # fundo xadrez discreto: mostra o efeito da opacidade
        xadrez = Image.new("RGBA", img.size, "#9AA0A6" if pal.escuro else "#D0D4DA")
        for y in range(0, img.size[1], 16):
            for x in range(0, img.size[0], 16):
                if (x // 16 + y // 16) % 2:
                    xadrez.paste("#7F858C" if pal.escuro else "#E4E7EB", (x, y, x + 16, y + 16))
        return Image.alpha_composite(xadrez, img)

    def atualizar(self) -> None:
        a = self.aparencia()
        pal = tema.paleta(a)
        self.l_opac.configure(text=f"{round(a.opacidade * 100)}%")
        for chave, amostra in self.amostras.items():
            cor = pal.destaque if chave == "destaque" else pal.fundo if chave == "fundo" else pal.grupos[chave]
            amostra.configure(bg=cor)
        self._foto = ImageTk.PhotoImage(self.imagem_previa())
        self.previa.configure(image=self._foto)

    def salvar(self) -> None:
        a = self.aparencia()
        erros = tema.validar(a)
        if erros:
            messagebox.showerror("Lotus", "\n".join(erros), parent=self)
            return
        tema.salvar(a)
        messagebox.showinfo(
            "Lotus",
            "Aparência salva. O painel flutuante usa na próxima vez que abrir; "
            "a janela principal, ao reabrir o Lotus.",
            parent=self,
        )
        self.destroy()
