"""Agente do atalho: roda em segundo plano e abre o painel flutuante.

Três threads, cada uma com uma função só (regra 11 do CLAUDE.md: threads não
recebem objetos do tkinter, só filas):

- gancho: instala o gancho de mouse e a tecla de atalho e roda o laço de
  mensagens do Windows. Só decide e enfileira; nunca bloqueia.
- trabalho: simula o clique, lê a seleção do Explorer (COM) e manda o
  resultado para a interface.
- principal (tkinter): mostra o painel, recarrega a configuração, executa
  os comandos do ícone ao lado do relógio e atende o pedido de parada.
- bandeja (bandeja.py): ícone e menu ao lado do relógio; só enfileira comandos.

O gancho só é instalado com o atalho ligado; com só o ícone ligado, o agente
roda sem ler nenhum evento de mouse.

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
from conversor.logs import get_logger, registrar_erros_tcl
from conversor.ui.icone import aplicar_icone

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
    """Ponto de entrada de `Lotus.exe --agente`: gancho do atalho (se ligado) e
    ícone ao lado do relógio (se ligado)."""
    import subprocess
    import tkinter as tk
    from tkinter import filedialog

    from conversor import shell
    from conversor.atalho import bandeja as bandeja_mod
    from conversor.atalho import controle
    from conversor.atalho.painel import abrir_painel
    from conversor.ui import icone

    log = get_logger()
    if not controle.precisa_rodar(config.carregar()):
        log.info("agente: atalho e ícone desligados; nada a fazer")
        return 0
    mutex = winapi.criar_mutex_unico()
    if mutex is None:
        log.info("agente já está rodando; esta instância vai sair")
        return 0
    parar_evt = winapi.criar_evento_parar()

    cfg = config.carregar()
    trabalho: queue.Queue = queue.Queue()
    saida: queue.Queue = queue.Queue()
    cliques: queue.Queue = queue.Queue()
    comandos: queue.Queue = queue.Queue()
    threading.Thread(target=trabalhador, args=(trabalho, saida), name="lotus-trabalho", daemon=True).start()

    estado = {"painel": None, "mtime": _mtime(config.arquivo_config()), "conta": 0,
              "gancho": None, "bandeja": None, "cfg": cfg}

    def ligar_gancho(g: config.Gatilho) -> None:
        gancho = Gancho(g, trabalho, cliques)
        gancho.start()
        gancho.pronto.wait(5)
        estado["gancho"] = gancho
        log.info("agente: atalho ligado: %s", g.descrever())

    def desligar_gancho() -> None:
        if estado["gancho"] is not None:
            estado["gancho"].parar()
            estado["gancho"].join(2)
            estado["gancho"] = None
            log.info("agente: atalho desligado")

    def aplicar(novo: config.Config) -> None:
        antigo, estado["cfg"] = estado["cfg"], novo
        if novo.atalho_ativo and estado["gancho"] is None:
            ligar_gancho(novo.gatilho)
        elif not novo.atalho_ativo:
            desligar_gancho()
        elif novo.gatilho != antigo.gatilho:
            estado["gancho"].recarregar(novo.gatilho)
            log.info("agente: atalho recarregado: %s", novo.gatilho.descrever())
        b = estado["bandeja"]
        if novo.bandeja and controle.BANDEJA_SUPORTADA and b is None:
            b = bandeja_mod.Bandeja(comandos, str(icone.caminho("lotus.ico")),
                                    novo.atalho_ativo, novo.gatilho.descrever())
            b.start()
            b.pronto.wait(5)
            estado["bandeja"] = b
        elif not novo.bandeja and b is not None:
            b.parar()
            estado["bandeja"] = None
        if estado["bandeja"] is not None:
            estado["bandeja"].atualizar(novo.atalho_ativo, novo.gatilho.descrever())

    estado["cfg"] = config.Config(gatilho=cfg.gatilho, atalho_ativo=False, bandeja=False)
    aplicar(cfg)
    log.info("agente iniciado (atalho %s; ícone %s)", "ligado" if cfg.atalho_ativo else "desligado",
             "ligado" if estado["bandeja"] is not None else "desligado")

    root = tk.Tk()
    registrar_erros_tcl(root)
    aplicar_icone(root)
    root.withdraw()

    def recarregar_config() -> None:
        estado["mtime"] = _mtime(config.arquivo_config())
        aplicar(config.carregar())

    def executar_comando(cmd: str) -> None:
        from conversor.atalho.janela_config import JanelaAtalho
        from conversor.ui.janela_aparencia import JanelaAparencia
        from conversor.ui.widgets import trazer_para_frente

        if cmd == bandeja_mod.ABRIR:
            subprocess.Popen(shell.launcher_command(), close_fds=True)
        elif cmd == bandeja_mod.CONVERTER:
            arquivos = list(filedialog.askopenfilenames(parent=root, title="Lotus — converter arquivos"))
            if arquivos:
                abrir_painel(root, arquivos, root.winfo_screenwidth() // 2, root.winfo_screenheight() // 2)
        elif cmd == bandeja_mod.ATALHO:
            controle.alternar_atalho()
            controle.ativar_inicio()
            recarregar_config()
        elif cmd == bandeja_mod.CONFIGURAR:
            trazer_para_frente(JanelaAtalho(root))
        elif cmd == bandeja_mod.APARENCIA:
            trazer_para_frente(JanelaAparencia(root))
        elif cmd == bandeja_mod.SAIR:
            log.info("agente: fechado pelo menu do ícone")
            root.destroy()

    def tick() -> None:
        if winapi.evento_sinalizado(parar_evt):
            log.info("agente: parada pedida")
            root.destroy()
            return
        for cmd in _esvaziar(comandos):
            try:
                executar_comando(cmd)
            except Exception:
                log.exception("agente: erro no comando %r do ícone", cmd)
            if cmd == bandeja_mod.SAIR:
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
        painel, gancho = estado["painel"], estado["gancho"]
        if gancho is not None:
            if painel is not None and not painel.fechado:
                gancho.painel_aberto.set()
                for cx, cy in _esvaziar(cliques):
                    painel.clique_global(cx, cy)
            else:
                gancho.painel_aberto.clear()
        estado["conta"] += 1
        if estado["conta"] % 40 == 0:  # a cada ~2 s: configuração mudou?
            if _mtime(config.arquivo_config()) != estado["mtime"]:
                recarregar_config()
                if not controle.precisa_rodar(estado["cfg"]):
                    log.info("agente: atalho e ícone desligados; saindo")
                    root.destroy()
                    return
        root.after(50, tick)

    root.after(50, tick)
    try:
        root.mainloop()
    finally:
        desligar_gancho()
        if estado["bandeja"] is not None:
            estado["bandeja"].parar()
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
