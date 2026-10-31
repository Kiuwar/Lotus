"""Janela "Aparência": estilo do painel (Vidro, Radial, Cartão), cor e
intensidade do vidro, animação, tamanho e claro/escuro — com prévia grande ao
vivo sobre um papel de parede de exemplo (claro, escuro ou foto)."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from conversor.ui import grupos, radial, render, tema, vidro

NOMES_MODO = {"auto": "Seguir o sistema", "claro": "Claro", "escuro": "Escuro"}
NOMES_FORMA = {"vidro": "Vidro", "radial": "Radial", "cartao": "Cartão"}
DESCRICAO_FORMA = {
    "vidro": "Pílulas de vidro em volta do arquivo, como os botões do iPhone.",
    "radial": "Formatos em volta do cursor, em faixas coloridas por grupo.",
    "cartao": "Lista em cartão, com uma seção por grupo.",
}
NOMES_TAMANHO = {"P": "Pequeno", "M": "Médio", "G": "Grande"}
NOMES_PAPEL = {"foto": "Foto", "claro": "Claro", "escuro": "Escuro"}
EXEMPLO = ["png", "jpg", "pdf", "docx", "txt", "xlsx", "stl"]
LADO_PREVIA = 420


class JanelaAparencia(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title("Lotus — aparência")
        self.resizable(False, False)
        self.atual = tema.carregar()
        self.cores: dict[str, str | None] = {"destaque": self.atual.destaque, "fundo": self.atual.fundo}
        self.cores_grupo: dict[str, str] = dict(self.atual.cores_grupo)

        self.v_tema = tk.StringVar(value=self.atual.tema)
        self.v_modo = tk.StringVar(value=self.atual.modo)
        self.v_forma = tk.StringVar(value=self.atual.forma)
        self.v_tamanho = tk.StringVar(value=self.atual.tamanho)
        self.v_opac = tk.IntVar(value=round(self.atual.opacidade * 100))
        self.v_moldura = tk.BooleanVar(value=self.atual.moldura_windows)
        self.v_vidro_cor = tk.StringVar(value=self.atual.vidro_cor)
        self.v_intens = tk.IntVar(value=round(self.atual.vidro_intensidade * 100))
        self.v_animacao = tk.BooleanVar(value=self.atual.animacao)
        self.v_papel = tk.StringVar(value="foto")

        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        esq = ttk.Frame(f)
        esq.grid(row=0, column=0, sticky="n")
        dir_ = ttk.Frame(f, padding=(18, 0, 0, 0))
        dir_.grid(row=0, column=1, sticky="n")

        # ---- estilo do painel ----
        self._titulo(esq, "Estilo do painel")
        fe = ttk.Frame(esq)
        fe.pack(anchor="w", pady=(4, 2))
        self.botoes_forma: dict[str, tk.Widget] = {}
        from conversor.ui.widgets import BotaoPilula

        for m, n in NOMES_FORMA.items():
            b = BotaoPilula(fe, n, command=lambda m=m: self._escolher_forma(m), largura=96, altura=32)
            b.pack(side="left", padx=(0, 6))
            self.botoes_forma[m] = b
        self.l_descricao = ttk.Label(esq, text="", foreground="#555", wraplength=330)
        self.l_descricao.pack(anchor="w", pady=(2, 10))

        # ---- vidro ----
        self.sec_vidro = ttk.Frame(esq)
        self._titulo(self.sec_vidro, "Cor do vidro")
        fc = ttk.Frame(self.sec_vidro)
        fc.pack(anchor="w", pady=(4, 8))
        self.bolinhas: dict[str, tk.Canvas] = {}
        fundo_janela = ttk.Style(self).lookup("TFrame", "background") or self.cget("background")
        for nome, cor in vidro.CORES.items():
            c = tk.Canvas(fc, width=30, height=30, highlightthickness=0, bd=0, cursor="hand2", bg=fundo_janela)
            c.pack(side="left", padx=(0, 6))
            c.bind("<Button-1>", lambda _e, n=nome: self._definir_vidro_cor(n))
            self.bolinhas[nome] = c
        ttk.Button(fc, text="Outra…", command=self._outra_cor_vidro).pack(side="left", padx=(4, 0))
        self._titulo(self.sec_vidro, "Intensidade")
        fi = ttk.Frame(self.sec_vidro)
        fi.pack(anchor="w", pady=(2, 6))
        ttk.Label(fi, text="Limpo").pack(side="left")
        ttk.Scale(fi, from_=0, to=100, variable=self.v_intens, length=200,
                  command=lambda _v: self.atualizar()).pack(side="left", padx=6)
        ttk.Label(fi, text="Fosco").pack(side="left")
        ttk.Checkbutton(self.sec_vidro, text="Animação de entrada (pílulas saem do arquivo)",
                        variable=self.v_animacao, command=self.atualizar).pack(anchor="w", pady=(0, 8))

        # ---- radial e cartão ----
        self.sec_outros = ttk.Frame(esq)
        self._titulo(self.sec_outros, "Tema e cores (Radial e Cartão)")
        fo = ttk.Frame(self.sec_outros)
        fo.pack(anchor="w", pady=(4, 0))
        ttk.Label(fo, text="Tema").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(fo, textvariable=self.v_tema, values=list(tema.PRESETS), state="readonly", width=18)
        cb.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())
        ttk.Label(fo, text="Opacidade").grid(row=1, column=0, sticky="w")
        fop = ttk.Frame(fo)
        fop.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Scale(fop, from_=60, to=100, variable=self.v_opac, length=150,
                  command=lambda _v: self.atualizar()).pack(side="left")
        self.l_opac = ttk.Label(fop, width=5)
        self.l_opac.pack(side="left", padx=6)
        fcores = ttk.Frame(self.sec_outros)
        fcores.pack(anchor="w", pady=(6, 8))
        self.amostras: dict[str, tk.Label] = {}
        alvos = [("destaque", "Destaque"), ("fundo", "Fundo"), *[(g, g) for g in tema.GRUPOS]]
        for i, (chave, nome) in enumerate(alvos):
            col = (i % 2) * 3
            amostra = tk.Label(fcores, width=3, relief="solid", bd=1, cursor="hand2")
            amostra.grid(row=i // 2, column=col, pady=2, sticky="w")
            amostra.bind("<Button-1>", lambda _e, c=chave: self.escolher_cor(c))
            ttk.Label(fcores, text=nome).grid(row=i // 2, column=col + 1, sticky="w", padx=(4, 2))
            ttk.Button(fcores, text="Padrão", width=7,
                       command=lambda c=chave: self.definir_cor(c, None)).grid(row=i // 2, column=col + 2, padx=(0, 10))
            self.amostras[chave] = amostra

        # ---- comuns ----
        self.sec_comum = ttk.Frame(esq)
        self._titulo(self.sec_comum, "Tamanho e janela")
        ft = ttk.Frame(self.sec_comum)
        ft.pack(anchor="w", pady=(4, 2))
        for m, n in NOMES_TAMANHO.items():
            ttk.Radiobutton(ft, text=n, value=m, variable=self.v_tamanho, command=self.atualizar).pack(side="left", padx=(0, 8))
        fm = ttk.Frame(self.sec_comum)
        fm.pack(anchor="w", pady=(2, 2))
        ttk.Label(fm, text="Claro/escuro:").pack(side="left", padx=(0, 6))
        for m, n in NOMES_MODO.items():
            ttk.Radiobutton(fm, text=n, value=m, variable=self.v_modo, command=self.atualizar).pack(side="left", padx=(0, 6))
        if sys.platform == "win32":
            ttk.Checkbutton(self.sec_comum, text="Usar a moldura padrão do Windows na janela principal",
                            variable=self.v_moldura).pack(anchor="w", pady=(4, 0))

        # ---- prévia ----
        self.previa = tk.Label(dir_, bd=0)
        self.previa.pack()
        fp = ttk.Frame(dir_)
        fp.pack(pady=(8, 0))
        ttk.Label(fp, text="Fundo da prévia:").pack(side="left", padx=(0, 6))
        for m, n in NOMES_PAPEL.items():
            ttk.Radiobutton(fp, text=n, value=m, variable=self.v_papel, command=self.atualizar).pack(side="left", padx=(0, 6))

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(bar, text="Restaurar padrão", command=self.padrao).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=4)
        BotaoPilula(bar, "Salvar", command=self.salvar, primario=True, largura=96).pack(side="left", padx=(4, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.atualizar()

    @staticmethod
    def _titulo(pai, texto: str) -> None:
        ttk.Label(pai, text=texto, font=("Helvetica", 12, "bold")).pack(anchor="w")

    # ---------- estado ----------

    def aparencia(self) -> tema.Aparencia:
        return replace(
            self.atual,
            tema=self.v_tema.get(), modo=self.v_modo.get(), forma=self.v_forma.get(),
            tamanho=self.v_tamanho.get(), opacidade=round(self.v_opac.get()) / 100,
            destaque=self.cores["destaque"], fundo=self.cores["fundo"],
            cores_grupo={g: c for g, c in self.cores_grupo.items() if c},
            moldura_windows=self.v_moldura.get(),
            vidro_cor=self.v_vidro_cor.get(), vidro_intensidade=round(self.v_intens.get()) / 100,
            animacao=self.v_animacao.get(),
        )

    def _escolher_forma(self, forma: str) -> None:
        self.v_forma.set(forma)
        self.atualizar()

    def _definir_vidro_cor(self, cor: str) -> None:
        self.v_vidro_cor.set(cor)
        self.atualizar()

    def _outra_cor_vidro(self) -> None:
        _, cor = colorchooser.askcolor(color=vidro.hex_da_cor(self.v_vidro_cor.get()), parent=self,
                                       title="Cor do vidro")
        if cor:
            self._definir_vidro_cor(cor.upper())

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
        p = tema.PADRAO
        self.v_tema.set(p.tema)
        self.v_modo.set(p.modo)
        self.v_forma.set(p.forma)
        self.v_tamanho.set(p.tamanho)
        self.v_opac.set(round(p.opacidade * 100))
        self.v_moldura.set(False)
        self.v_vidro_cor.set(p.vidro_cor)
        self.v_intens.set(round(p.vidro_intensidade * 100))
        self.v_animacao.set(p.animacao)
        self.atualizar()

    # ---------- prévia ----------

    def imagem_previa(self) -> Image.Image:
        from conversor.ui import render_vidro

        a = self.aparencia()
        pal = tema.paleta(a)
        lay = radial.montar(grupos.agrupar(EXEMPLO), a.forma, tema.TAMANHOS[a.tamanho] * 0.85)
        papel = render_vidro.papel_de_parede(LADO_PREVIA, LADO_PREVIA, self.v_papel.get())
        # O painel fica centrado no papel de parede; o vidro "vê" o que está atrás dele.
        ox, oy = (LADO_PREVIA - lay.largura) // 2, (LADO_PREVIA - lay.altura) // 2
        atras = papel.crop((ox, oy, ox + lay.largura, oy + lay.altura)) if lay.largura <= LADO_PREVIA else None
        img = render.Pintor(lay, pal, "exemplo.pdf", "pdf", a.opacidade, estilo=tema.estilo_vidro(a),
                            fundo_atras=atras).quadro(hover=lay.itens[0].fmt)
        if img.width > LADO_PREVIA or img.height > LADO_PREVIA:
            img.thumbnail((LADO_PREVIA, LADO_PREVIA), Image.LANCZOS)
            ox, oy = (LADO_PREVIA - img.width) // 2, (LADO_PREVIA - img.height) // 2
        base = papel.convert("RGBA")
        base.alpha_composite(img, (max(0, ox), max(0, oy)))
        # cantos arredondados, como um cartão de prévia
        mascara = Image.new("L", base.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *base.size), radius=18, fill=255)
        base.putalpha(mascara)
        return base

    def atualizar(self) -> None:
        a = self.aparencia()
        pal = tema.paleta(a)
        forma = a.forma
        for m, b in self.botoes_forma.items():
            b.primario = m == forma
            b._fotos.clear()
            b._desenhar()
        self.l_descricao.configure(text=DESCRICAO_FORMA[forma])
        for s in (self.sec_vidro, self.sec_outros, self.sec_comum):
            s.pack_forget()
        (self.sec_vidro if forma == "vidro" else self.sec_outros).pack(anchor="w", fill="x")
        self.sec_comum.pack(anchor="w", fill="x", pady=(4, 0))
        escolhida = vidro.hex_da_cor(a.vidro_cor)
        for nome, c in self.bolinhas.items():
            c.delete("all")
            cor = vidro.CORES[nome]
            ativa = cor.upper() == escolhida.upper() and (a.vidro_cor == nome or a.vidro_cor.startswith("#"))
            c.create_oval(3, 3, 27, 27, fill=cor, outline="#1D1D1F" if ativa else "#C7C7CC",
                          width=3 if ativa else 1)
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
