"""Painel flutuante do atalho: radial (padrão) ou cartão, estilo macOS.

Fluxo: abre centrado no cursor → passar o mouse destaca o formato → clicar
converte (a caixa mostra "…" e depois ✓ ou ✕) → fecha sozinho após o ✓,
ou com Esc, clique fora, clique no centro ou 15 s sem uso.

O desenho vem de conversor/ui (render + radial + tema); este módulo só cuida
da janela, dos eventos e da conversão em segundo plano (regra 11: a thread
recebe só dados).
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from conversor.core.detect import DetectionError, detect
from conversor.gui import common_targets, motivo_sem_destino
from conversor.logs import get_logger
from conversor.menu import Outcome, convert_many, summary
from conversor.ui import camadas, grupos, radial, render, tema

OCIOSO_MS = 15000
FECHAR_APOS_OK_MS = 1200
QUADROS_ENTRADA = 6       # animação de entrada: ~180 ms
INTERVALO_QUADRO_MS = 30


def recortar_escalado(tela, x: int, y: int, largura: int, altura: int, largura_logica: int):
    """O Pillow captura em pixels FÍSICOS (ImageGrab.grab liga o DPI por monitor);
    o agente trabalha em pixels lógicos. Com zoom de 150%, a escala é 1,5:
    recorta a área certa e volta ao tamanho lógico. Fora da tela: None."""
    escala = tela.width / max(1, largura_logica)
    caixa = (round(x * escala), round(y * escala), round((x + largura) * escala), round((y + altura) * escala))
    if caixa[0] < 0 or caixa[1] < 0 or caixa[2] > tela.width or caixa[3] > tela.height:
        return None  # outro monitor: vidro simulado
    return tela.crop(caixa).resize((largura, altura))


def capturar_fundo(x: int, y: int, largura: int, altura: int, largura_logica: int):
    """Windows: o que está na tela onde o painel vai aparecer (para o vidro de
    verdade). No Mac exigiria a permissão de Gravação de Tela: não captura."""
    if sys.platform != "win32":
        return None
    try:
        from PIL import ImageGrab

        tela = ImageGrab.grab()  # monitor principal, pixels físicos
        return recortar_escalado(tela, x, y, largura, altura, largura_logica)
    except Exception:  # noqa: BLE001 - sem captura, o vidro fica simulado
        get_logger().exception("captura do fundo para o vidro")
        return None


def _converter(resultados: list, caminhos: list[str], fmt: str) -> None:
    resultados.extend(convert_many(caminhos, fmt))


class Painel:
    def __init__(self, root: tk.Misc, arquivos: list[str], x: int, y: int,
                 aparencia: tema.Aparencia | None = None, forma: str | None = None):
        self.root = root
        self.arquivos = list(arquivos)
        self.aparencia = aparencia or tema.carregar()
        self.forma = forma or self.aparencia.forma
        self.cursor = (x, y)
        self.hover: str | None = None
        self.estados: dict[str, str] = {}
        self.ocupado = False
        self.dialogo = False   # caixa de mensagem aberta: não fechar por "clique fora"
        self.fechado = False
        self._ocioso = None
        # Todo `after` do painel passa por _depois: ao fechar, os pendentes são
        # cancelados. Senão o Tcl dispara um comando já apagado ("invalid
        # command name") e o Tk abre o diálogo de erro (no Mac, modal: trava).
        self._afters: set[str] = set()
        self.log = get_logger()

        formatos = []
        for a in self.arquivos:
            try:
                formatos.append(detect(Path(a)).fmt)
            except DetectionError:
                pass
        self.origem = formatos[0] if formatos else "?"
        self.destinos = common_targets(formatos)
        self.motivo = None if self.destinos else (motivo_sem_destino(formatos) or "Arquivo não reconhecido.")

        nome = Path(self.arquivos[0]).name if len(self.arquivos) == 1 else f"{len(self.arquivos)} arquivos"
        escala = tema.TAMANHOS.get(self.aparencia.tamanho, 1.0)
        self.layout = radial.montar(grupos.agrupar(self.destinos), self.forma, escala)
        self.pal = tema.paleta(self.aparencia)

        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        px, py = radial.posicionar(self.layout, x, y, self.top.winfo_screenwidth(), self.top.winfo_screenheight())
        self.pos = (px, py)
        fundo = None
        if self.forma == "vidro":  # captura ANTES de a janela aparecer
            fundo = capturar_fundo(px, py, self.layout.largura, self.layout.altura,
                                   self.top.winfo_screenwidth())
        self.pintor = render.Pintor(self.layout, self.pal, nome, self.origem, self.aparencia.opacidade,
                                    estilo=tema.estilo_vidro(self.aparencia), fundo_atras=fundo)
        self.superficie = camadas.criar(self.top, px, py, self.layout.largura, self.layout.altura, self.pal.fundo)
        self.progresso = 1.0
        if self.forma == "vidro" and self.aparencia.animacao:
            self.progresso = 0.0
            self._animar()
        else:
            self._pintar()

        self.top.bind("<Motion>", self._mover)
        self.top.bind("<Leave>", lambda _e: self._set_hover(None))
        self.top.bind("<Button-1>", self._clicar)
        self.top.bind("<Escape>", lambda _e: self.destroy())
        # Janela destruída por fora (ex.: a raiz fechou): cancela os after também.
        self.top.bind("<Destroy>", lambda e: self._encerrar() if e.widget is self.top else None, add="+")
        if sys.platform != "win32":
            # No Windows o "clique fora" vem do gancho de mouse do agente
            # (clique_global): a janela de ferramenta pode perder o foco ao surgir.
            self.top.bind("<FocusOut>", lambda _e: self._fora())
        self._rastrear()
        self.top.focus_force()
        # De novo após a janela aparecer de fato: sem foco, o Esc não chega.
        self._depois(30, self.top.focus_force)
        self._reiniciar_ocioso()
        if self.motivo:
            self._depois(50, self._sem_destino)

    def _depois(self, ms: int, func, *args) -> str | None:
        """`after` que se desfaz sozinho quando o painel fecha."""
        if self.fechado:
            return None

        def rodar():
            self._afters.discard(ident)
            if not self.fechado:
                func(*args)

        ident = self.top.after(ms, rodar)
        self._afters.add(ident)
        return ident

    def _cancelar(self, ident: str | None) -> None:
        if ident is not None and ident in self._afters:
            self._afters.discard(ident)
            self.top.after_cancel(ident)

    # ---------- desenho ----------

    def _pintar(self) -> None:
        if not self.fechado:
            self.superficie.mostrar(self.pintor.quadro(self.hover, self.estados, self.progresso))

    def _animar(self) -> None:
        """Pílulas saem do arquivo para a órbita (cada quadro via _depois: regra 22)."""
        self.progresso = min(1.0, self.progresso + 1 / QUADROS_ENTRADA)
        self._pintar()
        if self.progresso < 1.0:
            self._depois(INTERVALO_QUADRO_MS, self._animar)

    def _set_hover(self, alvo: str | None) -> None:
        if alvo != self.hover:
            self.hover = alvo
            self._pintar()

    # ---------- eventos ----------

    def _mover(self, e) -> None:
        self._set_hover(self.layout.hit_test(e.x, e.y))
        self._reiniciar_ocioso()

    def _rastrear(self) -> None:
        """Acompanha o cursor consultando a posição (não depende só de <Motion>,
        que pode não chegar numa janela em camadas)."""
        if self.fechado:
            return
        try:
            px, py = self.top.winfo_pointerxy()
        except tk.TclError:
            return
        if self.contem(px, py):
            alvo = self.layout.hit_test(px - self.pos[0], py - self.pos[1])
            if alvo != self.hover:
                self._set_hover(alvo)
                self._reiniciar_ocioso()
        elif self.hover is not None:
            self._set_hover(None)
        self._depois(30, self._rastrear)

    def _clicar(self, e) -> None:
        alvo = self.layout.hit_test(e.x, e.y)
        if alvo is None:
            return
        if alvo == radial.CENTRO:
            self.destroy()
        elif alvo == radial.MAIS:
            # "Mais…": troca pelo cartão com todos os formatos, no mesmo lugar.
            x, y = self.cursor
            self.destroy()
            Painel(self.root, self.arquivos, x, y, self.aparencia, forma="cartao")
        elif not self.ocupado:
            self.converter(alvo)

    def contem(self, x: int, y: int) -> bool:
        """(x, y) da tela cai numa parte visível do painel?"""
        lx, ly = x - self.pos[0], y - self.pos[1]
        if not (0 <= lx < self.layout.largura and 0 <= ly < self.layout.altura):
            return False
        if self.layout.forma == "radial":
            return (lx - self.layout.ancora_x) ** 2 + (ly - self.layout.ancora_y) ** 2 <= self.layout.fundo_r ** 2
        return True

    def clique_global(self, x: int, y: int) -> None:
        """Chamado pelo agente a cada clique em qualquer lugar da tela."""
        if not self.contem(x, y):
            self._fora()

    def _fora(self) -> None:
        if not self.ocupado and not self.dialogo:
            self.destroy()

    def _reiniciar_ocioso(self) -> None:
        self._cancelar(self._ocioso)
        self._ocioso = self._depois(OCIOSO_MS, self._fora)

    # ---------- conversão ----------

    def converter(self, fmt: str) -> None:
        self.ocupado = True
        self.estados = {fmt: "ocupado"}
        self._pintar()
        resultados: list[Outcome] = []
        t = threading.Thread(target=_converter, args=(resultados, list(self.arquivos), fmt), daemon=True)
        t.start()
        self._esperar(t, resultados, fmt)

    def _esperar(self, t: threading.Thread, resultados: list, fmt: str) -> None:
        if self.fechado:
            return
        if t.is_alive():
            self._depois(80, self._esperar, t, resultados, fmt)
            return
        self.ocupado = False
        falhou, texto = summary(resultados)
        self.estados = {fmt: "erro" if falhou else "ok"}
        self._pintar()
        if falhou:
            self.dialogo = True
            messagebox.showerror("Lotus", texto, parent=self.top)
            self.dialogo = False
            self.estados = {}
            self._pintar()
        else:
            self.log.info("painel: %s", texto.replace("\n", " | "))
            self._depois(FECHAR_APOS_OK_MS, self.destroy)

    def _sem_destino(self) -> None:
        self.dialogo = True
        messagebox.showinfo("Lotus", self.motivo, parent=self.top)
        self.destroy()

    # ---------- fim ----------

    def destroy(self) -> None:
        if self.fechado:
            return
        self._encerrar()
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def _encerrar(self) -> None:
        self.fechado = True
        for ident in list(self._afters):
            try:
                self.top.after_cancel(ident)
            except tk.TclError:
                pass
        self._afters.clear()


def abrir_painel(root: tk.Misc, arquivos: list[str], x: int, y: int) -> Painel:
    return Painel(root, arquivos, x, y)
