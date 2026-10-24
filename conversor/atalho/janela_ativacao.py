"""Janela "Ativar o painel no Mac": passos que se atualizam sozinhos (3 do
painel por atalho, a Ação Rápida e, opcional, o atalho de teclado dela).

Aberta na 1ª vez que o Lotus abre no Mac, pelo indicador da janela principal,
por Ferramentas e pelo agente quando o gancho de cliques falha.

Regra 11: as threads (ligar o agente, testar o Finder) só recebem dados e uma
fila. Regra 22: todo `after` pendente é cancelado ao fechar e no <Destroy>.
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from conversor.atalho import ativacao_mac as am

INTERVALO_MS = 1000
VERDE, CINZA = "#1E8E3E", "#8E8E93"


def _ligar(fila: queue.Queue) -> None:
    from conversor.atalho import controle

    try:
        fila.put(("mensagem", controle.ativar()))
    except Exception as e:  # noqa: BLE001 - vira mensagem na janela
        fila.put(("mensagem", f"Não foi possível ligar: {e}"))


def _testar_finder(fila: queue.Queue) -> None:
    from conversor.atalho.diagnostico_mac import testar_automacao

    fila.put(("automacao", testar_automacao(limite=60)))


def _instalar_acao_rapida(fila: queue.Queue) -> None:
    from conversor import acao_rapida

    try:
        acao_rapida.instalar()
        fila.put(("mensagem", "Ação Rápida instalada."))
    except Exception as e:  # noqa: BLE001
        fila.put(("mensagem", f"Não foi possível instalar a Ação Rápida: {e}"))


ACOES_PADRAO = {
    "ligar": lambda fila: threading.Thread(target=_ligar, args=(fila,), daemon=True).start(),
    "testar_finder": lambda fila: threading.Thread(target=_testar_finder, args=(fila,), daemon=True).start(),
    "acao_rapida": lambda fila: threading.Thread(target=_instalar_acao_rapida, args=(fila,), daemon=True).start(),
}


class JanelaAtivacao(tk.Toplevel):
    def __init__(self, master, coletor=am.coletar_estado, acoes: dict | None = None,
                 abrir=am.abrir_ajustes, ao_fechar=None):
        super().__init__(master)
        self.title("Ativar o painel no Mac")
        self.resizable(False, False)
        self.coletor, self.abrir, self.ao_fechar = coletor, abrir, ao_fechar
        self.acoes = {**ACOES_PADRAO, **(acoes or {})}
        self.fila: queue.Queue = queue.Queue()
        self.automacao: str | None = None
        self.ajustes_abertos_em: float | None = None
        self.fechado = False
        self._pendente = None
        self.passos: list[am.Passo] = []

        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Ative o Lotus no Mac",
                  font=("Helvetica", 15, "bold")).pack(anchor="w")
        ttk.Label(f, text="Esta janela se atualiza sozinha. Nada sai do seu Mac.",
                  foreground="#555").pack(anchor="w", pady=(2, 12))
        self.linhas = []
        for _ in range(5):
            linha = ttk.Frame(f)
            linha.pack(fill="x", pady=6)
            marca = ttk.Label(linha, text="", width=2, font=("Helvetica", 16, "bold"))
            marca.pack(side="left", anchor="n")
            texto = ttk.Frame(linha)
            texto.pack(side="left", fill="x", expand=True, padx=(8, 8))
            titulo = ttk.Label(texto, text="", font=("Helvetica", 13, "bold"))
            titulo.pack(anchor="w")
            expl = ttk.Label(texto, text="", wraplength=380, justify="left")
            expl.pack(anchor="w")
            dica = ttk.Label(texto, text="", wraplength=380, justify="left", foreground="#8a5a00")
            dica.pack(anchor="w")
            botao = ttk.Button(linha, text="")
            self.linhas.append((marca, titulo, expl, dica, botao, texto))
        self.rodape = ttk.Label(f, text="", wraplength=460, justify="left")
        self.rodape.pack(anchor="w", pady=(12, 0))
        barra = ttk.Frame(f)
        barra.pack(fill="x", pady=(12, 0))
        ttk.Button(barra, text="Fechar", command=self.fechar).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Destroy>", self._ao_destruir, add="+")
        self.atualizar()

    # ---------- ciclo ----------

    def _estado(self) -> dict:
        e = dict(self.coletor(self.automacao))
        e["automacao"] = self.automacao
        e["segundos_desde_ajustes"] = (None if self.ajustes_abertos_em is None
                                       else time.monotonic() - self.ajustes_abertos_em)
        return e

    def atualizar(self) -> None:
        self._pendente = None
        if self.fechado:
            return
        while True:
            try:
                tipo, valor = self.fila.get_nowait()
            except queue.Empty:
                break
            if tipo == "automacao":
                self.automacao = valor
            elif tipo == "mensagem":
                self.rodape.configure(text=valor)
        self.passos = am.passos(self._estado())
        for p, (marca, titulo, expl, dica, botao, texto) in zip(self.passos, self.linhas):
            marca.configure(text="✓" if p.feito else str(p.numero), foreground=VERDE if p.feito else CINZA)
            titulo.configure(text=p.titulo)
            expl.configure(text=p.explicacao)
            dica.configure(text=p.dica)
            if p.botao:
                botao.configure(text=p.botao, command=lambda a=p.acao: self.executar(a))
                if not botao.winfo_manager():
                    botao.pack(side="right", anchor="n", before=texto)
            else:
                botao.pack_forget()
        if am.tudo_pronto(self.passos):
            self.rodape.configure(text="Tudo pronto! Experimente o atalho sobre um arquivo no Finder.")
        self._pendente = self.after(INTERVALO_MS, self.atualizar)

    def executar(self, acao: str) -> None:
        if acao in ("acessibilidade", "automacao", "teclado"):
            self.ajustes_abertos_em = time.monotonic()
            if not self.abrir(acao):
                self.rodape.configure(text="Não foi possível abrir os Ajustes do Sistema. Abra-os pelo "
                                           "menu  → Ajustes do Sistema → Privacidade e Segurança.")
            return
        if acao == "testar_finder":
            self.automacao = "testando"
        self.acoes[acao](self.fila)
        self.atualizar_ja()

    def atualizar_ja(self) -> None:
        if self._pendente is not None:
            self.after_cancel(self._pendente)
            self._pendente = None
        self.atualizar()

    # ---------- fechar ----------

    def _cancelar(self) -> None:
        if self._pendente is not None:
            try:
                self.after_cancel(self._pendente)
            except tk.TclError:
                pass
            self._pendente = None

    def _ao_destruir(self, evento) -> None:
        if evento.widget is self:
            self.fechado = True
            self._cancelar()

    def fechar(self) -> None:
        self.fechado = True
        self._cancelar()
        if self.ao_fechar is not None:
            self.ao_fechar()
        self.destroy()


def abrir(master, **kw) -> JanelaAtivacao:
    from conversor.ui.widgets import trazer_para_frente

    j = JanelaAtivacao(master, **kw)
    trazer_para_frente(j)
    return j
