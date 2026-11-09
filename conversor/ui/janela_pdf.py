"""Janelas "Separar PDF" e "Juntar em um PDF".

O trabalho roda numa thread que recebe só dados e uma fila (regra 11); todo
`after` pendente é cancelado ao fechar (regra 22).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from conversor.core import engine


def mover(itens: list, indice: int, delta: int) -> int:
    """Move itens[indice] em `delta` posições; devolve o novo índice (lógica pura)."""
    novo = max(0, min(len(itens) - 1, indice + delta))
    if novo != indice:
        itens.insert(novo, itens.pop(indice))
    return novo


def _trabalhar(fila: queue.Queue, fn, args) -> None:
    try:
        fila.put(("ok", fn(*args)))
    except engine.ConversionError as e:
        fila.put(("erro", str(e)))
    except Exception as e:  # nunca morrer em silêncio
        fila.put(("erro", f"Erro inesperado: {e!r}"))


class _Base(tk.Toplevel):
    def __init__(self, master, titulo: str, ao_concluir=None):
        super().__init__(master)
        self.title(titulo)
        self.resizable(True, False)
        self._fila: queue.Queue = queue.Queue()
        self._pendente = None
        self._ao_concluir = ao_concluir
        self.resultado: engine.ResultadoPaginas | None = None
        self.erro: str | None = None
        self.corpo = ttk.Frame(self, padding=14)
        self.corpo.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda _e: self.fechar())
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Destroy>", self._ao_destruir, add="+")

    def _rodape(self, texto_ok: str) -> None:
        rod = ttk.Frame(self.corpo)
        rod.grid(row=99, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(rod, text="Cancelar", command=self.fechar).pack(side="right")
        self.botao_ok = ttk.Button(rod, text=texto_ok, command=self.executar)
        self.botao_ok.pack(side="right", padx=8)
        self.situacao = ttk.Label(self.corpo, text="", wraplength=420, justify="left")
        self.situacao.grid(row=98, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _iniciar(self, fn, args) -> None:
        self.botao_ok.configure(state="disabled")
        self.situacao.configure(text="Trabalhando…")
        threading.Thread(target=_trabalhar, args=(self._fila, fn, args), daemon=True).start()
        self._pendente = self.after(100, self._esperar)

    def _esperar(self) -> None:
        self._pendente = None
        try:
            tipo, valor = self._fila.get_nowait()
        except queue.Empty:
            self._pendente = self.after(100, self._esperar)
            return
        self.botao_ok.configure(state="normal")
        if tipo == "erro":
            self.erro = valor
            self.situacao.configure(text="")
            messagebox.showerror("Lotus", valor, parent=self)
            return
        self.resultado = valor
        if self._ao_concluir:
            self._ao_concluir(valor)
        self.fechar()

    def fechar(self) -> None:
        self._cancelar()
        if self.winfo_exists():
            self.destroy()

    def _cancelar(self) -> None:
        if self._pendente is not None:
            try:
                self.after_cancel(self._pendente)
            except tk.TclError:
                pass
            self._pendente = None

    def _ao_destruir(self, evento) -> None:
        if evento.widget is self:
            self._cancelar()


class JanelaSeparar(_Base):
    def __init__(self, master, pdf: str | Path, ao_concluir=None, out_dir: str | None = None):
        super().__init__(master, "Separar PDF", ao_concluir)
        self.pdf = Path(pdf)
        self.out_dir = out_dir
        try:
            from conversor.converters.pdf_paginas import total_paginas

            total = total_paginas(self.pdf)
            info = f"{self.pdf.name} — {total} página{'s' if total != 1 else ''}"
        except Exception as e:  # senha, PDF danificado: a mensagem certa aparece ao separar
            total, info = None, f"{self.pdf.name} ({e})"
        self.total = total
        c = self.corpo
        ttk.Label(c, text=info, font=("Helvetica", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.modo = tk.StringVar(value=engine.SEPARAR_INTERVALOS)
        ttk.Radiobutton(c, text="Um PDF para cada intervalo (ex.: 1-3, 4-9, 10-)",
                        value=engine.SEPARAR_INTERVALOS, variable=self.modo).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Radiobutton(c, text="Um PDF só com estas páginas, nesta ordem (ex.: 2, 5-7)",
                        value=engine.SEPARAR_EXTRAIR, variable=self.modo).grid(
            row=2, column=0, columnspan=3, sticky="w")
        ttk.Label(c, text="Páginas:").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.paginas = tk.StringVar(value=f"1-{total}" if total else "")
        campo = ttk.Entry(c, textvariable=self.paginas, width=36)
        campo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(10, 0))
        campo.focus_set()
        campo.bind("<Return>", lambda _e: self.executar())
        ttk.Label(c, text="\"8-\" vai da página 8 até o fim. O PDF original não é alterado.").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        c.columnconfigure(1, weight=1)
        self._rodape("Separar")

    def executar(self) -> None:
        self._iniciar(engine.separar_pdf, (self.pdf, self.paginas.get(), self.modo.get(), self.out_dir))


class JanelaJuntar(_Base):
    def __init__(self, master, arquivos: list[str | Path], ao_concluir=None):
        super().__init__(master, "Juntar em um PDF", ao_concluir)
        self.arquivos = [Path(a) for a in arquivos]
        c = self.corpo
        ttk.Label(c, text="Ordem das páginas no PDF final (PDFs e imagens):").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.lista = tk.Listbox(c, height=10, width=52, activestyle="none", exportselection=False)
        self.lista.grid(row=1, column=0, rowspan=4, sticky="nsew", pady=(6, 0))
        botoes = ttk.Frame(c)
        botoes.grid(row=1, column=1, sticky="n", padx=(8, 0), pady=(6, 0))
        ttk.Button(botoes, text="↑ Subir", command=lambda: self._mover(-1)).pack(fill="x")
        ttk.Button(botoes, text="↓ Descer", command=lambda: self._mover(1)).pack(fill="x", pady=4)
        ttk.Button(botoes, text="Remover", command=self._remover).pack(fill="x")
        ttk.Label(c, text="Salvar como:").grid(row=5, column=0, sticky="w", pady=(10, 0))
        linha = ttk.Frame(c)
        linha.grid(row=6, column=0, columnspan=2, sticky="ew")
        primeiro = self.arquivos[0] if self.arquivos else Path("juntos.pdf")
        self.destino = tk.StringVar(
            value=str(primeiro.parent / f"{primeiro.stem} + {max(len(self.arquivos) - 1, 1)}.pdf"))
        ttk.Entry(linha, textvariable=self.destino, width=46).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Escolher…", command=self._escolher).pack(side="left", padx=(6, 0))
        c.columnconfigure(0, weight=1)
        self._rodape("Juntar")
        self._redesenhar(0)

    def _redesenhar(self, selecionado: int | None) -> None:
        self.lista.delete(0, "end")
        for n, a in enumerate(self.arquivos, 1):
            self.lista.insert("end", f"{n}.  {a.name}")
        if selecionado is not None and self.arquivos:
            self.lista.selection_set(selecionado)
            self.lista.see(selecionado)

    def _selecionado(self) -> int | None:
        sel = self.lista.curselection()
        return sel[0] if sel else None

    def _mover(self, delta: int) -> None:
        i = self._selecionado()
        if i is not None:
            self._redesenhar(mover(self.arquivos, i, delta))

    def _remover(self) -> None:
        i = self._selecionado()
        if i is not None:
            self.arquivos.pop(i)
            self._redesenhar(min(i, len(self.arquivos) - 1) if self.arquivos else None)

    def _escolher(self) -> None:
        atual = Path(self.destino.get() or "juntos.pdf")
        nome = filedialog.asksaveasfilename(
            parent=self, title="Salvar PDF", defaultextension=".pdf",
            initialdir=str(atual.parent), initialfile=atual.name, filetypes=[("PDF", "*.pdf")])
        if nome:
            self.destino.set(nome)

    def executar(self) -> None:
        if len(self.arquivos) < 2:
            messagebox.showinfo("Lotus", "Deixe pelo menos 2 arquivos na lista.", parent=self)
            return
        self._iniciar(engine.juntar_pdf, (list(self.arquivos), self.destino.get().strip() or None))
