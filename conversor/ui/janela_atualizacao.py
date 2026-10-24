"""Janela "Atualizar o Lotus": procurar → baixar (com progresso) → reiniciar.

A internet só é usada depois de a pessoa clicar em "Procurar agora" (ou dizer
"Sim" ao lembrete mensal). Regra 11: as threads recebem só dados e a fila.
Regra 22: o `after` de leitura da fila é cancelado ao fechar e no <Destroy>.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from conversor import __version__, atualizar

AVISO_PRIVACIDADE = ("Para procurar, o Lotus acessa o GitHub (github.com), onde as versões são "
                     "publicadas. Nenhum arquivo ou dado seu é enviado; o GitHub vê apenas o seu "
                     "endereço IP, como em qualquer site.")


def _procurar(fila: queue.Queue, procurar) -> None:
    try:
        fila.put(("achou", procurar()))
    except Exception as e:  # noqa: BLE001 - vira mensagem na janela
        fila.put(("erro", str(e)))


def _baixar(fila: queue.Queue, baixar, versao, cancelar: threading.Event) -> None:
    try:
        caminho = baixar(versao, progresso=lambda f, t: fila.put(("progresso", (f, t))),
                         cancelado=cancelar.is_set)
        fila.put(("baixado", caminho))
    except Exception as e:  # noqa: BLE001
        fila.put(("erro", str(e)))


def _aplicar(fila: queue.Queue, aplicar, caminho) -> None:
    try:
        aplicar(caminho)
        fila.put(("aplicado", None))
    except Exception as e:  # noqa: BLE001
        fila.put(("erro", str(e)))


class JanelaAtualizacao(tk.Toplevel):
    def __init__(self, master, ao_reiniciar, procurar=atualizar.procurar, baixar=atualizar.baixar,
                 aplicar=atualizar.aplicar, ja_autorizado: bool = False):
        super().__init__(master)
        self.title("Atualizar o Lotus")
        self.resizable(False, False)
        self.ao_reiniciar = ao_reiniciar
        self.fn = {"procurar": procurar, "baixar": baixar, "aplicar": aplicar}
        self.fila: queue.Queue = queue.Queue()
        self.cancelar = threading.Event()
        self.versao = None
        self.arquivo = None
        self.estado = "inicio"
        self.fechado = False
        self._pendente = None

        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Atualizar o Lotus", font=("Helvetica", 15, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"Versão instalada: {__version__}", foreground="#555").pack(anchor="w")
        self.msg = ttk.Label(f, text=AVISO_PRIVACIDADE, wraplength=440, justify="left")
        self.msg.pack(anchor="w", pady=(12, 6))
        self.notas = tk.Text(f, height=8, width=58, wrap="word", state="disabled", bd=1)
        self.barra = ttk.Progressbar(f, mode="determinate", length=440)
        self.botoes = ttk.Frame(f)
        self.botoes.pack(fill="x", pady=(12, 0))
        self.b_principal = ttk.Button(self.botoes, text="Procurar agora", command=self.procurar)
        self.b_principal.pack(side="right")
        self.b_fechar = ttk.Button(self.botoes, text="Fechar", command=self.fechar)
        self.b_fechar.pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Destroy>", self._ao_destruir, add="+")
        if ja_autorizado:
            self.procurar()

    # ---------- etapas ----------

    def _thread(self, alvo, *args) -> None:
        threading.Thread(target=alvo, args=(self.fila, *args), daemon=True).start()
        if self._pendente is None:
            self._pendente = self.after(100, self._ler_fila)

    def procurar(self) -> None:
        self.estado = "procurando"
        self.msg.configure(text="Procurando a versão mais recente…")
        self.b_principal.configure(state="disabled")
        self._thread(_procurar, self.fn["procurar"])

    def baixar(self) -> None:
        self.estado = "baixando"
        self.msg.configure(text=f"Baixando a versão {self.versao.numero}…")
        self.barra.pack(anchor="w", pady=(4, 0), before=self.botoes)
        self.b_principal.configure(state="disabled")
        self.b_fechar.configure(text="Cancelar")
        self._thread(_baixar, self.fn["baixar"], self.versao, self.cancelar)

    def reiniciar(self) -> None:
        self.estado = "aplicando"
        self.msg.configure(text="Preparando a instalação…")
        self.b_principal.configure(state="disabled")
        self._thread(_aplicar, self.fn["aplicar"], self.arquivo)

    def _ler_fila(self) -> None:
        self._pendente = None
        if self.fechado:
            return
        while True:
            try:
                tipo, valor = self.fila.get_nowait()
            except queue.Empty:
                break
            self._tratar(tipo, valor)
        if self.estado in ("procurando", "baixando", "aplicando"):
            self._pendente = self.after(100, self._ler_fila)

    def _tratar(self, tipo: str, valor) -> None:
        if tipo == "erro":
            self.estado = "erro"
            self.msg.configure(text=valor)
            self.b_fechar.configure(text="Fechar")
            self.b_principal.configure(text="Tentar de novo", state="normal", command=self.procurar)
        elif tipo == "achou" and valor is None:
            self.estado = "atualizado"
            self.msg.configure(text=f"Você já tem a versão mais recente ({__version__}).")
            self.b_principal.pack_forget()
        elif tipo == "achou":
            self.estado = "disponivel"
            self.versao = valor
            mb = f" ({valor.tamanho / 1e6:.0f} MB)" if valor.tamanho else ""
            self.msg.configure(text=f"Versão {valor.numero} disponível{mb}. Suas configurações "
                                    "(atalho, aparência, menu) são mantidas.")
            self.notas.configure(state="normal")
            self.notas.delete("1.0", "end")
            self.notas.insert("1.0", valor.notas.strip()[:3000] or "(sem notas)")
            self.notas.configure(state="disabled")
            self.notas.pack(anchor="w", pady=(4, 0), before=self.botoes)
            self.b_principal.configure(text="Baixar e instalar", state="normal", command=self.baixar)
        elif tipo == "progresso":
            feito, total = valor
            if total:
                self.barra.configure(maximum=total, value=feito)
        elif tipo == "baixado":
            self.estado = "pronto"
            self.arquivo = valor
            self.b_fechar.configure(text="Depois")
            self.msg.configure(text="Pronto para instalar. O Lotus vai fechar, atualizar e abrir de "
                                    "novo sozinho. Suas configurações são mantidas.")
            self.b_principal.configure(text="Reiniciar agora", state="normal", command=self.reiniciar)
        elif tipo == "aplicado":
            self.estado = "fim"
            self.fechar()
            self.ao_reiniciar()

    # ---------- fechar ----------

    def _cancelar_after(self) -> None:
        if self._pendente is not None:
            try:
                self.after_cancel(self._pendente)
            except tk.TclError:
                pass
            self._pendente = None

    def _ao_destruir(self, evento) -> None:
        if evento.widget is self:
            self.fechado = True
            self.cancelar.set()
            self._cancelar_after()

    def fechar(self) -> None:
        if self.fechado:
            return
        self.fechado = True
        self.cancelar.set()  # interrompe um download em andamento
        self._cancelar_after()
        self.destroy()


def abrir(master, ao_reiniciar, **kw) -> JanelaAtualizacao:
    from conversor.ui.widgets import trazer_para_frente

    j = JanelaAtualizacao(master, ao_reiniciar, **kw)
    trazer_para_frente(j)
    return j
