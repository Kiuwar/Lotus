"""Painel por atalho no macOS (Finder e área de trabalho).

- Gancho: Quartz Event Tap (pyobjc), numa thread com o próprio run loop.
  Exige a permissão de Acessibilidade; sem ela CGEventTapCreate devolve None
  e o Lotus explica como liberar.
- Só vale quando o clique cai numa janela do Finder (inclui a Mesa, cujos
  ícones também são do Finder).
- Seleção: AppleScript ao Finder (osascript). Exige a permissão de Automação.
- Instância única: trava de arquivo (fcntl). Parada: arquivo-sinal.
- Início automático: LaunchAgent em ~/Library/LaunchAgents (por usuário).

Mapeamento das teclas: ctrl=⌃ Control, shift=⇧ Shift, alt=⌥ Option, win=⌘ Command.
Todos os nomes do Quartz/AppKit usados aqui são conferidos no CI do Mac
(tests/test_mac.py::test_pyobjc_names_exist).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import queue
import subprocess
import threading
import time
from pathlib import Path

from conversor.atalho import config, gesto
from conversor.logs import get_logger, registrar_erros_tcl
from conversor.ui.icone import aplicar_icone

FINDER = "com.apple.finder"
MSG_SEM_ACESSIBILIDADE = ("Sem permissão de Acessibilidade. Como resolver: Ajustes do Sistema → "
                          "Privacidade e Segurança → Acessibilidade → ative o Lotus.")
INTERVALO_TENTATIVA = 2.0     # s entre novas tentativas de instalar o gancho
TENTATIVAS_COM_PERMISSAO = 3  # com a permissão dada e o gancho ainda falhando: reinicia o agente
JANELA_REINICIO = 120.0       # não reinicia de novo se já reiniciou há menos que isto (s)
MARCA = 0x4C4F5455  # "LOTU": identifica cliques simulados pelo próprio Lotus
ROTULO_LAUNCHD = "com.kiuwar.lotus.agente"

NOMES_QUARTZ = [
    "CGEventTapCreate", "CGEventMaskBit", "CGEventTapEnable", "CFMachPortCreateRunLoopSource",
    "CFRunLoopAddSource", "CFRunLoopGetCurrent", "CFRunLoopRun", "CFRunLoopStop",
    "kCFRunLoopCommonModes", "CGEventGetFlags", "CGEventGetLocation", "CGEventGetIntegerValueField",
    "CGEventSetIntegerValueField", "CGEventCreateMouseEvent", "CGEventSetFlags", "CGEventPost",
    "kCGHIDEventTap", "kCGSessionEventTap", "kCGHeadInsertEventTap", "kCGEventTapOptionDefault",
    "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGEventRightMouseDown", "kCGEventRightMouseUp",
    "kCGEventOtherMouseDown", "kCGEventOtherMouseUp", "kCGEventTapDisabledByTimeout",
    "kCGEventTapDisabledByUserInput", "kCGMouseEventButtonNumber", "kCGEventSourceUserData",
    "kCGMouseButtonLeft", "kCGEventFlagMaskControl", "kCGEventFlagMaskShift",
    "kCGEventFlagMaskAlternate", "kCGEventFlagMaskCommand", "CGWindowListCopyWindowInfo",
    "kCGWindowListOptionOnScreenOnly", "kCGNullWindowID", "kCGWindowBounds", "kCGWindowOwnerPID",
    "CGEventCreate",
]


# Application Services (HIServices), chamado por ctypes (sem dependência nova).
# Conferido na documentação da Apple: AXIsProcessTrusted() -> Bool, macOS 10.4+,
# "Returns whether the current process is a trusted accessibility client."
APPLICATION_SERVICES = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
NOMES_AX = ["AXIsProcessTrusted"]


def ax_confiavel() -> bool | None:
    """True/False: este processo tem a permissão de Acessibilidade. None: não deu para saber."""
    import ctypes

    try:
        lib = ctypes.cdll.LoadLibrary(APPLICATION_SERVICES)
        fn = lib.AXIsProcessTrusted
    except (OSError, AttributeError):
        get_logger().exception("AXIsProcessTrusted indisponível")
        return None
    fn.argtypes = []
    fn.restype = ctypes.c_bool  # Boolean (unsigned char) em C
    return bool(fn())


# ---------- lógica pura (testada em qualquer sistema) ----------

def mods_de_flags(flags: int, mascaras: dict[str, int]) -> set[str]:
    return {m for m, bit in mascaras.items() if flags & bit}


def botao_de(tipo: str, numero: int) -> str:
    """tipo: "esquerdo" | "direito" | "outro"; numero = kCGMouseEventButtonNumber."""
    if tipo != "outro":
        return tipo
    return {2: "meio", 3: "lateral1", 4: "lateral2"}.get(numero, f"botao{numero}")


def janela_no_ponto(janelas: list[dict], x: float, y: float) -> dict | None:
    """Primeira janela (de cima para baixo) cujo retângulo contém o ponto."""
    for j in janelas:
        b = j.get("kCGWindowBounds") or {}
        if b and b["X"] <= x < b["X"] + b["Width"] and b["Y"] <= y < b["Y"] + b["Height"]:
            return j
    return None


SCRIPT_SELECAO = """
set saida to ""
tell application "Finder"
    repeat with item_ in (get selection)
        set saida to saida & POSIX path of (item_ as alias) & linefeed
    end repeat
end tell
return saida
"""


def ler_selecao_finder(executar=subprocess.run) -> list[str]:
    r = executar(["osascript", "-e", SCRIPT_SELECAO], capture_output=True, text=True, timeout=8)
    if r.returncode != 0:
        erro = (r.stderr or "").strip()
        if "-1743" in erro:  # errAEEventNotPermitted
            raise PermissionError(
                "O macOS bloqueou o acesso ao Finder. Como resolver: Ajustes do Sistema → "
                "Privacidade e Segurança → Automação → Lotus → marque \"Finder\"."
            )
        raise RuntimeError(f"osascript: {erro}")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


# ---------- instância única, parada e início automático ----------

def _arq(nome: str) -> Path:
    return config.pasta_config() / nome


def travar_instancia():
    """Arquivo aberto e travado se esta é a única instância; None se já há outra."""
    import fcntl

    _arq("agente.lock").parent.mkdir(parents=True, exist_ok=True)
    f = open(_arq("agente.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.write(str(os.getpid()))
    f.flush()
    return f


def agente_rodando() -> bool:
    import fcntl

    p = _arq("agente.lock")
    if not p.exists():
        return False
    with open(p) as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
        return False


def pedir_parada() -> bool:
    if not agente_rodando():
        return False
    _arq("parar").touch()
    return True


def parada_pedida() -> bool:
    p = _arq("parar")
    if p.exists():
        p.unlink(missing_ok=True)
        return True
    return False


def gravar_estado_agente(gancho_ok: bool, erro: str | None, ax: bool | None) -> None:
    """Relatório do agente para o diagnóstico (a janela de aviso pode ter ficado
    escondida; este arquivo não some)."""
    import sys

    estado = {"pid": os.getpid(), "inicio": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
              "gancho_ok": gancho_ok, "erro": erro, "ax_confiavel": ax, "executavel": sys.executable}
    try:
        _arq("estado-agente.json").write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    except OSError:
        get_logger().exception("não foi possível gravar o estado do agente")


def ler_estado_agente() -> dict | None:
    """Relatório do agente que está rodando agora (None se não há ou é de um agente antigo)."""
    try:
        estado = json.loads(_arq("estado-agente.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not agente_rodando():
        return None
    try:
        dono = int(_arq("agente.lock").read_text().strip() or 0)
    except (OSError, ValueError):
        dono = 0
    return estado if not dono or estado.get("pid") == dono else None


def plist_launchd(programa: list[str]) -> bytes:
    return plistlib.dumps({
        "Label": ROTULO_LAUNCHD,
        "ProgramArguments": [*programa, "--agente"],
        "RunAtLoad": True,
        "ProcessType": "Interactive",
    })


def arquivo_launchd() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{ROTULO_LAUNCHD}.plist"


# ---------- gancho Quartz ----------

def deve_reiniciar(tentativas_com_permissao: int, ultimo_reinicio: float | None, agora: float) -> bool:
    """Permissão dada, mas o gancho segue falhando: o macOS pode só aceitar a
    permissão num processo novo. Reinicia uma vez; se já reiniciou há pouco,
    não insiste (evita laço) e a janela guiada sugere remover/adicionar."""
    if tentativas_com_permissao < TENTATIVAS_COM_PERMISSAO:
        return False
    return ultimo_reinicio is None or agora - ultimo_reinicio > JANELA_REINICIO


def ultimo_reinicio() -> float | None:
    try:
        return _arq("reinicio").stat().st_mtime
    except OSError:
        return None


class GanchoMac(threading.Thread):
    def __init__(self, gatilho: config.Gatilho, trabalho: queue.Queue, cliques: queue.Queue | None = None,
                 avisos: queue.Queue | None = None):
        super().__init__(name="lotus-gancho-mac", daemon=True)
        import Quartz

        self.Q = Quartz
        self.detector = gesto.Detector(gatilho)
        self.trabalho, self.cliques, self.avisos = trabalho, cliques, avisos
        self._parar = threading.Event()
        self.painel_aberto = threading.Event()
        self.pronto = threading.Event()
        self.erro: str | None = None
        self._loop = None
        self._tap = None
        self.mascaras = {
            "ctrl": Quartz.kCGEventFlagMaskControl, "shift": Quartz.kCGEventFlagMaskShift,
            "alt": Quartz.kCGEventFlagMaskAlternate, "win": Quartz.kCGEventFlagMaskCommand,
        }
        self.tipos = {
            Quartz.kCGEventLeftMouseDown: ("esquerdo", True), Quartz.kCGEventLeftMouseUp: ("esquerdo", False),
            Quartz.kCGEventRightMouseDown: ("direito", True), Quartz.kCGEventRightMouseUp: ("direito", False),
            Quartz.kCGEventOtherMouseDown: ("outro", True), Quartz.kCGEventOtherMouseUp: ("outro", False),
        }
        self.log = get_logger()

    def _app_no_ponto(self, x: float, y: float) -> str:
        Q = self.Q
        janelas = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly, Q.kCGNullWindowID) or []
        j = janela_no_ponto([dict(w) for w in janelas], x, y)
        if not j:
            return ""
        from AppKit import NSRunningApplication

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(j.get("kCGWindowOwnerPID", 0))
        return str(app.bundleIdentifier() or "") if app else ""

    def _callback(self, proxy, tipo, evento, refcon):
        Q = self.Q
        try:
            if tipo in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                Q.CGEventTapEnable(self._tap, True)  # o macOS desliga taps lentos; religa
                return evento
            if tipo not in self.tipos:
                return evento
            nome, apertou = self.tipos[tipo]
            botao = botao_de(nome, Q.CGEventGetIntegerValueField(evento, Q.kCGMouseEventButtonNumber))
            injetado = Q.CGEventGetIntegerValueField(evento, Q.kCGEventSourceUserData) == MARCA
            ponto = Q.CGEventGetLocation(evento)
            mods = mods_de_flags(Q.CGEventGetFlags(evento), self.mascaras) if apertou else set()
            classe = ""
            if apertou and not injetado and botao == self.detector.gatilho.botao:
                # O detector aceita "CabinetWClass"; no Mac, Finder = janela aceita.
                classe = "CabinetWClass" if self._app_no_ponto(ponto.x, ponto.y) == FINDER else ""
            acao = self.detector.evento(botao, apertou, mods, injetado, classe)
            if (apertou and not injetado and acao == gesto.PASSAR and self.cliques is not None
                    and self.painel_aberto.is_set()):
                self.cliques.put((round(ponto.x), round(ponto.y)))
            if acao == gesto.DISPARAR:
                self.trabalho.put(("mouse", 0, round(ponto.x), round(ponto.y), frozenset(mods)))
            if acao in (gesto.DISPARAR, gesto.ENGOLIR):
                return None  # engole: o Finder não recebe
        except Exception:
            self.log.exception("erro no gancho do Mac")
        return evento

    def _criar_tap(self):
        Q = self.Q
        mascara = 0
        for t in self.tipos:
            mascara |= Q.CGEventMaskBit(t)
        return Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                  Q.kCGEventTapOptionDefault, mascara, self._callback, None)

    def _avisar(self, *msg) -> None:
        if self.avisos is not None:
            self.avisos.put(msg)

    def run(self) -> None:
        Q = self.Q
        self._tap = self._criar_tap()
        tentou_de_novo = False
        com_permissao = 0
        while self._tap is None:
            if self.erro is None:
                self.erro = MSG_SEM_ACESSIBILIDADE
                self.log.error(self.erro)
            self.pronto.set()
            # Espera a permissão chegar e tenta de novo (antes, o agente desistia
            # e só um desligar/ligar resolvia).
            if self._parar.wait(INTERVALO_TENTATIVA):
                return
            if ax_confiavel():
                tentou_de_novo = True
                self._tap = self._criar_tap()
                if self._tap is None:
                    com_permissao += 1
                    if deve_reiniciar(com_permissao, ultimo_reinicio(), time.time()):
                        self.log.warning("permissão dada, gancho ainda falha: reiniciando o agente")
                        self._avisar("reiniciar")
                        return
        self.erro = None
        if tentou_de_novo:
            self.log.info("gancho instalado depois que a permissão de Acessibilidade chegou")
            self._avisar("gancho_ok")
        fonte = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, fonte, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self.pronto.set()
        Q.CFRunLoopRun()

    def recarregar(self, g: config.Gatilho) -> None:
        self.detector = gesto.Detector(g)

    def parar(self) -> None:
        self._parar.set()
        if self._loop is not None:
            self.Q.CFRunLoopStop(self._loop)


def clicar_simples(x: int, y: int) -> None:
    """Clique esquerdo sem modificadores, marcado como do Lotus (o gancho o ignora)."""
    import Quartz as Q

    for tipo in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
        ev = Q.CGEventCreateMouseEvent(None, tipo, (x, y), Q.kCGMouseButtonLeft)
        Q.CGEventSetFlags(ev, 0)
        Q.CGEventSetIntegerValueField(ev, Q.kCGEventSourceUserData, MARCA)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)


def posicao_mouse() -> tuple[int, int]:
    """Onde está o ponteiro (coordenadas do Quartz, origem no canto superior esquerdo)."""
    import Quartz as Q

    p = Q.CGEventGetLocation(Q.CGEventCreate(None))
    return round(p.x), round(p.y)


def trabalhador(trabalho: queue.Queue, saida: queue.Queue) -> None:
    """("mouse", 0, x, y, mods): clique com o atalho (seleciona o item clicado e lê).
    ("selecao", x, y): menu da barra de menus (lê o que já está selecionado)."""
    log = get_logger()
    while True:
        item = trabalho.get()
        if item is None:
            return
        try:
            if item[0] == "selecao":
                _, x, y = item
            else:
                _, _, x, y, _ = item
                clicar_simples(x, y)   # seleciona só o item clicado (como no Windows)
                time.sleep(0.15)
            arquivos = [c for c in ler_selecao_finder() if os.path.isfile(c)]
            if arquivos:
                saida.put(("painel", arquivos, x, y))
            elif item[0] == "selecao":
                saida.put(("aviso", "Selecione um ou mais arquivos no Finder e escolha de novo "
                                    "\"Converter os arquivos selecionados no Finder…\"."))
        except PermissionError as e:
            saida.put(("aviso", str(e)))
        except Exception:
            log.exception("erro ao ler a seleção do Finder")


def executar() -> int:
    """`Lotus --agente` no Mac: gancho de cliques (se o painel estiver ligado) e
    ícone na barra de menus (se ligado). Relê a configuração sozinho: ligar ou
    desligar no app vale na hora, sem reiniciar o agente."""
    import tkinter as tk
    from tkinter import messagebox

    from conversor import shell
    from conversor.atalho import controle
    from conversor.atalho.painel import abrir_painel

    log = get_logger()
    trava = travar_instancia()
    if trava is None:
        log.info("agente (Mac) já está rodando")
        return 0
    parada_pedida()  # descarta sinal antigo

    trabalho: queue.Queue = queue.Queue()
    saida: queue.Queue = queue.Queue()
    cliques: queue.Queue = queue.Queue()
    comandos: queue.Queue = queue.Queue()
    threading.Thread(target=trabalhador, args=(trabalho, saida), daemon=True).start()

    root = tk.Tk()
    registrar_erros_tcl(root)
    aplicar_icone(root)
    root.withdraw()
    try:  # agente sem ícone no Dock
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        log.exception("não foi possível esconder o ícone do Dock")
    estado = {"painel": None, "guia": None, "ajuda": None, "reiniciar": False, "gancho": None,
              "barra": None, "cfg": None, "mtime": None, "ticks": 0}

    def trazer_app() -> None:
        try:
            from AppKit import NSApplication

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            log.exception("não foi possível trazer o Lotus para a frente")

    def mostrar_guia() -> None:
        # Antes era um aviso que podia ficar escondido atrás das janelas (o agente
        # não tem ícone no Dock). Agora: a janela guiada, trazida para a frente.
        from conversor.atalho import janela_ativacao

        g = estado["guia"]
        if g is not None and not g.fechado:
            g.lift()
            return
        trazer_app()
        estado["guia"] = janela_ativacao.abrir(root)

    def mostrar_ajuda() -> None:
        from conversor.ui import janela_ajuda

        a = estado["ajuda"]
        if a is not None and a.winfo_exists():
            a.lift()
            return
        trazer_app()
        estado["ajuda"] = janela_ajuda.abrir(root, acoes={"Ativar o painel no Mac…": mostrar_guia})

    def ligar_gancho(cfg: config.Config) -> None:
        g = GanchoMac(cfg.gatilho, trabalho, cliques, avisos=saida)
        g.start()
        g.pronto.wait(5)
        estado["gancho"] = g
        gravar_estado_agente(g.erro is None and g.pronto.is_set(),
                             g.erro or (None if g.pronto.is_set() else "o gancho não respondeu em 5 s"),
                             ax_confiavel())
        if g.erro:
            mostrar_guia()

    def desligar_gancho() -> None:
        g = estado["gancho"]
        if g is not None:
            g.parar()
            estado["gancho"] = None
        gravar_estado_agente(None, "painel por atalho desligado", ax_confiavel())

    def icone() -> str:
        from conversor.ui.icone import RECURSOS

        return str(RECURSOS / "lotus.png")

    def aplicar(cfg: config.Config) -> None:
        anterior = estado["cfg"]
        estado["cfg"] = cfg
        g = estado["gancho"]
        if cfg.atalho_ativo and g is None:
            ligar_gancho(cfg)
        elif not cfg.atalho_ativo and g is not None:
            desligar_gancho()
        elif cfg.atalho_ativo and anterior is not None and cfg.gatilho != anterior.gatilho:
            g.recarregar(cfg.gatilho)
        elif not cfg.atalho_ativo and anterior is None:
            gravar_estado_agente(None, "painel por atalho desligado", ax_confiavel())
        b = estado["barra"]
        try:
            if cfg.bandeja and b is None:
                from conversor.atalho.barra_mac import BarraMac

                estado["barra"] = BarraMac(comandos, icone(), cfg.atalho_ativo, cfg.gatilho.descrever())
            elif not cfg.bandeja and b is not None:
                b.remover()
                estado["barra"] = None
            elif b is not None:
                b.atualizar(cfg.atalho_ativo, cfg.gatilho.descrever())
        except Exception:
            log.exception("ícone na barra de menus")

    def reler_config() -> bool:
        """True se o agente ainda precisa rodar."""
        try:
            mtime = config.arquivo_config().stat().st_mtime
        except OSError:
            mtime = None
        if estado["cfg"] is not None and mtime == estado["mtime"]:
            return True
        estado["mtime"] = mtime
        cfg = config.carregar()
        if not controle.precisa_rodar(cfg):
            return False
        aplicar(cfg)
        return True

    def comando(cmd: str) -> None:
        from conversor.atalho import barra_mac as bm

        if cmd == bm.CONVERTER:
            x, y = posicao_mouse()
            trabalho.put(("selecao", x, y))
        elif cmd == bm.ABRIR:
            subprocess.Popen(shell.launcher_command(), start_new_session=True, close_fds=True)
        elif cmd == bm.ATALHO:
            controle.alternar_atalho()  # o reler_config aplica na hora
        elif cmd == bm.ATIVAR:
            mostrar_guia()
        elif cmd == bm.AJUDA:
            mostrar_ajuda()
        elif cmd == bm.SAIR:
            # Não usa controle.desativar_bandeja(): ela esperaria este mesmo agente
            # parar (travaria o menu). Grava e deixa o reler_config encerrar.
            cfg = config.carregar()
            cfg.bandeja = False
            config.salvar(cfg)
            if not controle.precisa_rodar(cfg):
                controle.desativar_inicio()

    def tick() -> None:
        if parada_pedida():
            root.destroy()
            return
        estado["ticks"] += 1
        if estado["ticks"] % 20 == 0 and not reler_config():  # ~1 s
            log.info("agente (Mac): nada mais ligado; encerrando")
            root.destroy()
            return
        while not comandos.empty():
            comando(comandos.get_nowait())
        while not saida.empty():
            msg = saida.get_nowait()
            if msg[0] == "aviso":
                trazer_app()
                messagebox.showwarning("Lotus", msg[1])
                continue
            if msg[0] == "gancho_ok":
                gravar_estado_agente(True, None, ax_confiavel())
                continue
            if msg[0] == "reiniciar":
                estado["reiniciar"] = True
                root.destroy()
                return
            _, arquivos, x, y = msg
            if estado["painel"] is not None:
                estado["painel"].destroy()
            while not cliques.empty():
                cliques.get_nowait()
            trazer_app()
            estado["painel"] = abrir_painel(root, arquivos, x, y)
        p, g = estado["painel"], estado["gancho"]
        if g is not None:
            if p is not None and not p.fechado:
                g.painel_aberto.set()
                while not cliques.empty():
                    p.clique_global(*cliques.get_nowait())
            else:
                g.painel_aberto.clear()
        root.after(50, tick)

    if not reler_config():
        log.info("agente (Mac): painel e ícone desligados; nada a fazer")
        root.destroy()
        trabalho.put(None)
        trava.close()
        return 0
    root.after(50, tick)
    try:
        root.mainloop()
    finally:
        if estado["gancho"] is not None:
            estado["gancho"].parar()
        if estado["barra"] is not None:
            try:
                estado["barra"].remover()
            except Exception:
                log.exception("remover o ícone da barra de menus")
        trabalho.put(None)
        trava.close()
    if estado["reiniciar"]:
        reiniciar_agente()
    return 0


def reiniciar_agente() -> None:
    """Um agente novo (a trava deste já foi solta). Marca o horário para não entrar em laço."""
    from conversor import shell

    _arq("reinicio").touch()
    subprocess.Popen(shell.launcher_command() + ["--agente"], start_new_session=True, close_fds=True)
