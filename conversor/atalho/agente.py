"""Agente do atalho: roda em segundo plano e abre o painel flutuante.

Três threads, cada uma com uma função só (regra 11 do CLAUDE.md: threads não
recebem objetos do tkinter, só filas):

- gancho: instala o gancho de mouse e a tecla de atalho e roda o laço de
  mensagens do Windows. Só decide e enfileira; nunca bloqueia.
- trabalho: simula o clique, lê a seleção do Explorer (COM) e manda o
  resultado para a interface.
- principal (tkinter): mostra o painel, recarrega a configuração e atende o
  pedido de parada.

O que o gancho vê: só eventos de botão do mouse. Nada é gravado nem enviado;
nenhuma tecla digitada é lida (a tecla de atalho usa RegisterHotKey, que só
avisa daquela combinação).
"""

from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes as w
from pathlib import Path

from conversor.atalho import config, gesto, selecao, winapi
from conversor.logs import get_logger

ID_TECLA = 0x4C54  # identificador da tecla de atalho registrada ("LT")
MSG_RECARREGAR = winapi.WM_APP + 1


class Gancho(threading.Thread):
    def __init__(self, gatilho: config.Gatilho, trabalho: queue.Queue, cliques: queue.Queue | None = None):
        super().__init__(name="lotus-gancho", daemon=True)
        self.detector = gesto.Detector(gatilho)
        self.gatilho = gatilho
        self.novo_gatilho: config.Gatilho | None = None
        self.trabalho = trabalho
        # Cliques em qualquer lugar da tela, só enquanto há painel aberto
        # (para fechá-lo ao clicar fora). Só posição; nada é gravado.
        self.cliques = cliques
        self.painel_aberto = threading.Event()
        self.tid = 0
        self.pronto = threading.Event()
        self.erro: str | None = None
        self._hook = None
        self._proc = winapi.HOOKPROC(self._callback)  # referência mantida: não pode ser coletada
        self.log = get_logger()

    # chamado pelo Windows a cada evento de mouse: precisa ser muito rápido
    def _callback(self, ncode, wparam, lparam):
        try:
            if ncode == 0 and wparam in winapi.MOUSE_MSGS:
                info = ctypes.cast(lparam, ctypes.POINTER(winapi.MSLLHOOKSTRUCT)).contents
                botao, apertou = winapi.MOUSE_MSGS[wparam]
                if botao == "x":
                    botao = "lateral1" if (info.mouseData >> 16) == 1 else "lateral2"
                injetado = bool(info.flags & (winapi.LLMHF_INJECTED | winapi.LLMHF_LOWER_IL_INJECTED))
                classe, filho = "", ""
                if apertou and not injetado and botao == self.detector.gatilho.botao:
                    classe, filho = winapi.classes_no_ponto(info.pt.x, info.pt.y)
                mods = winapi.modificadores_pressionados() if apertou else set()
                acao = self.detector.evento(botao, apertou, mods, injetado, classe, filho)
                if (apertou and not injetado and acao == gesto.PASSAR and self.cliques is not None
                        and self.painel_aberto.is_set()):
                    self.cliques.put((info.pt.x, info.pt.y))
                if acao == gesto.DISPARAR:
                    hwnd = winapi.janela_raiz_no_ponto(info.pt.x, info.pt.y)
                    self.trabalho.put(("mouse", int(hwnd or 0), info.pt.x, info.pt.y, frozenset(mods)))
                if acao in (gesto.DISPARAR, gesto.ENGOLIR):
                    return 1  # engole o evento: o Explorer não o recebe
        except Exception:
            self.log.exception("erro no gancho de mouse")
        return winapi.user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _registrar_tecla(self) -> None:
        winapi.user32.UnregisterHotKey(None, ID_TECLA)
        g = self.gatilho
        if g.tipo != "tecla":
            return
        flags = winapi.MOD_NOREPEAT
        for m in g.modificadores:
            flags |= winapi.MOD_FLAGS[m]
        if not winapi.user32.RegisterHotKey(None, ID_TECLA, flags, config.vk_da_tecla(g.tecla)):
            self.erro = f"O atalho {g.descrever()} já está em uso por outro programa."
            self.log.warning(self.erro)

    def run(self) -> None:
        self.tid = winapi.kernel32.GetCurrentThreadId()
        self._hook = winapi.user32.SetWindowsHookExW(
            winapi.WH_MOUSE_LL, self._proc, winapi.kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook:
            self.erro = f"Falha ao instalar o gancho de mouse ({ctypes.get_last_error()})."
            self.log.error(self.erro)
        self._registrar_tecla()
        self.pronto.set()
        msg = w.MSG()
        try:
            while winapi.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == winapi.WM_HOTKEY and msg.wParam == ID_TECLA:
                    hwnd = winapi.user32.GetForegroundWindow()
                    x, y = winapi.posicao_cursor()
                    classe_fg = winapi.classe(hwnd)
                    if classe_fg in gesto.CLASSES_EXPLORER or gesto.eh_mesa(classe_fg):
                        self.trabalho.put(("tecla", int(hwnd), x, y, frozenset()))
                elif msg.message == MSG_RECARREGAR and self.novo_gatilho is not None:
                    self.gatilho = self.novo_gatilho
                    self.detector = gesto.Detector(self.gatilho)
                    self.erro = None
                    self._registrar_tecla()
        finally:
            winapi.user32.UnregisterHotKey(None, ID_TECLA)
            if self._hook:
                winapi.user32.UnhookWindowsHookEx(self._hook)

    def recarregar(self, g: config.Gatilho) -> None:
        self.novo_gatilho = g
        winapi.user32.PostThreadMessageW(self.tid, MSG_RECARREGAR, 0, 0)

    def parar(self) -> None:
        if self.tid:
            winapi.user32.PostThreadMessageW(self.tid, winapi.WM_QUIT, 0, 0)


def trabalhador(trabalho: queue.Queue, saida: queue.Queue) -> None:
    """Thread de trabalho: transforma um gesto em lista de arquivos."""
    selecao.iniciar_com()
    log = get_logger()
    while True:
        item = trabalho.get()
        if item is None:
            return
        tipo, hwnd, x, y, mods = item
        try:
            ler = selecao.selecoes_mesa if gesto.eh_mesa(winapi.classe(hwnd)) else (
                lambda h=hwnd: selecao.selecoes(h))
            if tipo == "mouse":
                antes = ler()
                winapi.soltar_modificadores_e_clicar(set(mods))
                caminhos: list[str] = []
                for _ in range(10):  # o Explorer atualiza a seleção em alguns ms
                    time.sleep(0.05)
                    caminhos = gesto.escolher_aba(antes, ler())
                    if caminhos:
                        break
            else:
                abas = ler()
                caminhos = next((c for c in abas.values() if c), [])
            arquivos = selecao.apenas_arquivos(caminhos)
            if arquivos:
                saida.put(("painel", arquivos, x, y))
            else:
                log.info("gesto sem arquivo selecionado (caminhos=%r)", caminhos)
        except Exception:
            log.exception("erro ao ler a seleção do Explorer")


def executar() -> int:
    """Ponto de entrada de `Lotus.exe --agente`."""
    import tkinter as tk

    from conversor.atalho.painel import abrir_painel

    log = get_logger()
    mutex = winapi.criar_mutex_unico()
    if mutex is None:
        log.info("agente já está rodando; esta instância vai sair")
        return 0
    parar_evt = winapi.criar_evento_parar()

    cfg = config.carregar()
    trabalho: queue.Queue = queue.Queue()
    saida: queue.Queue = queue.Queue()
    cliques: queue.Queue = queue.Queue()
    gancho = Gancho(cfg.gatilho, trabalho, cliques)
    gancho.start()
    gancho.pronto.wait(5)
    threading.Thread(target=trabalhador, args=(trabalho, saida), name="lotus-trabalho", daemon=True).start()
    log.info("agente iniciado: %s", cfg.gatilho.descrever())

    root = tk.Tk()
    root.withdraw()
    estado = {"painel": None, "mtime": _mtime(config.arquivo_config()), "conta": 0}

    def tick() -> None:
        if winapi.evento_sinalizado(parar_evt):
            log.info("agente: parada pedida")
            root.destroy()
            return
        try:
            while True:
                _, arquivos, x, y = saida.get_nowait()
                if estado["painel"] is not None:
                    try:
                        estado["painel"].destroy()
                    except tk.TclError:
                        pass
                _esvaziar(cliques)  # cliques anteriores ao painel não contam como "fora"
                estado["painel"] = abrir_painel(root, arquivos, x, y)
        except queue.Empty:
            pass
        painel = estado["painel"]
        if painel is not None and not painel.fechado:
            gancho.painel_aberto.set()
            for cx, cy in _esvaziar(cliques):
                painel.clique_global(cx, cy)
        else:
            gancho.painel_aberto.clear()
        estado["conta"] += 1
        if estado["conta"] % 40 == 0:  # a cada ~2 s: configuração mudou?
            m = _mtime(config.arquivo_config())
            if m != estado["mtime"]:
                estado["mtime"] = m
                novo = config.carregar()
                gancho.recarregar(novo.gatilho)
                log.info("agente: atalho recarregado: %s", novo.gatilho.descrever())
        root.after(50, tick)

    root.after(50, tick)
    try:
        root.mainloop()
    finally:
        gancho.parar()
        trabalho.put(None)
        winapi.kernel32.CloseHandle(parar_evt)
        winapi.kernel32.CloseHandle(mutex)
    return 0


def _esvaziar(q: queue.Queue) -> list:
    itens = []
    while True:
        try:
            itens.append(q.get_nowait())
        except queue.Empty:
            return itens


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0
