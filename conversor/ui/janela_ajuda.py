"""Janela de Ajuda: abas com o conteúdo de conversor/ajuda.py (sem internet).

O único link (página do projeto) só abre o navegador se a pessoa clicar.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from conversor import ajuda


class JanelaAjuda(tk.Toplevel):
    def __init__(self, master, acoes: dict | None = None, sistema: str | None = None):
        """acoes: rótulo do botão -> função (ex.: "Diagnosticar e reparar")."""
        super().__init__(master)
        self.title("Ajuda do Lotus")
        self.geometry("620x480")
        self.minsize(480, 360)
        # O rodapé entra primeiro (lado de baixo): o texto não pode empurrá-lo para fora.
        self.rodape = ttk.Frame(self, padding=10)
        self.rodape.pack(side="bottom", fill="x")
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.textos: dict[str, tk.Text] = {}
        for nome, blocos in ajuda.secoes(sistema):
            quadro = ttk.Frame(self.abas, padding=8)
            texto = tk.Text(quadro, wrap="word", bd=0, highlightthickness=0, padx=6, pady=6, height=10,
                            font=("Helvetica", 12), cursor="arrow")
            barra = ttk.Scrollbar(quadro, command=texto.yview)
            texto.configure(yscrollcommand=barra.set)
            barra.pack(side="right", fill="y")
            texto.pack(fill="both", expand=True)
            texto.tag_configure("titulo", font=("Helvetica", 15, "bold"), spacing1=4, spacing3=8)
            texto.tag_configure("texto", spacing3=8)
            texto.tag_configure("passo", lmargin1=14, lmargin2=28, spacing3=4)
            for tipo, conteudo in blocos:
                texto.insert("end", conteudo + "\n", tipo)
            texto.configure(state="disabled")
            self.abas.add(quadro, text=nome)
            self.textos[nome] = texto

        barra = self.rodape
        ttk.Button(barra, text="Fechar", command=self.destroy).pack(side="right")
        ttk.Button(barra, text="Página do projeto", command=lambda: webbrowser.open(ajuda.PAGINA)).pack(
            side="right", padx=(0, 8))
        for rotulo, funcao in (acoes or {}).items():
            ttk.Button(barra, text=rotulo, command=funcao).pack(side="left", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())


def abrir(master, **kw) -> JanelaAjuda:
    from conversor.ui.widgets import trazer_para_frente

    j = JanelaAjuda(master, **kw)
    trazer_para_frente(j)
    return j
