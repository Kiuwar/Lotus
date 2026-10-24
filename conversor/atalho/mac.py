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

import os
import plistlib
import queue
import subprocess
import threading
import time
from pathlib import Path

from conversor.atalho import config, gesto
from conversor.logs import get_logger, registrar_erros_tcl

FINDER = "com.apple.finder"
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
]


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

class GanchoMac(threading.Thread):
    def __init__(self, gatilho: config.Gatilho, trabalho: queue.Queue, cliques: queue.Queue | None = None):
        super().__init__(name="lotus-gancho-mac", daemon=True)
        import Quartz

        self.Q = Quartz
        self.detector = gesto.Detector(gatilho)
        self.trabalho, self.cliques = trabalho, cliques
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

    def run(self) -> None:
        Q = self.Q
        mascara = 0
        for t in self.tipos:
            mascara |= Q.CGEventMaskBit(t)
        self._tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                       Q.kCGEventTapOptionDefault, mascara, self._callback, None)
        if self._tap is None:
            self.erro = ("Sem permissão de Acessibilidade. Como resolver: Ajustes do Sistema → "
                         "Privacidade e Segurança → Acessibilidade → ative o Lotus.")
            self.log.error(self.erro)
            self.pronto.set()
            return
        fonte = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = Q.CFRunLoopGetCurrent()
        Q.CFRunLoopAddSource(self._loop, fonte, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        self.pronto.set()
        Q.CFRunLoopRun()

    def recarregar(self, g: config.Gatilho) -> None:
        self.detector = gesto.Detector(g)

    def parar(self) -> None:
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


def trabalhador(trabalho: queue.Queue, saida: queue.Queue) -> None:
    log = get_logger()
    while True:
        item = trabalho.get()
        if item is None:
            return
        _, _, x, y, _ = item
        try:
            clicar_simples(x, y)       # seleciona só o item clicado (como no Windows)
            time.sleep(0.15)
            arquivos = [c for c in ler_selecao_finder() if os.path.isfile(c)]
            if arquivos:
                saida.put(("painel", arquivos, x, y))
        except PermissionError as e:
            saida.put(("aviso", str(e)))
        except Exception:
            log.exception("erro ao ler a seleção do Finder")


def executar() -> int:
    """`Lotus --agente` no Mac."""
    import tkinter as tk
    from tkinter import messagebox

    from conversor.atalho.painel import abrir_painel

    log = get_logger()
    trava = travar_instancia()
    if trava is None:
        log.info("agente (Mac) já está rodando")
        return 0
    parada_pedida()  # descarta sinal antigo

    cfg = config.carregar()
    trabalho: queue.Queue = queue.Queue()
    saida: queue.Queue = queue.Queue()
    cliques: queue.Queue = queue.Queue()
    gancho = GanchoMac(cfg.gatilho, trabalho, cliques)
    gancho.start()
    gancho.pronto.wait(5)
    threading.Thread(target=trabalhador, args=(trabalho, saida), daemon=True).start()

    root = tk.Tk()
    registrar_erros_tcl(root)
    root.withdraw()
    try:  # agente sem ícone no Dock
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        log.exception("não foi possível esconder o ícone do Dock")
    if gancho.erro:
        messagebox.showwarning("Lotus", gancho.erro)
    estado = {"painel": None}

    def tick() -> None:
        if parada_pedida():
            root.destroy()
            return
        while not saida.empty():
            msg = saida.get_nowait()
            if msg[0] == "aviso":
                messagebox.showwarning("Lotus", msg[1])
                continue
            _, arquivos, x, y = msg
            if estado["painel"] is not None:
                estado["painel"].destroy()
            while not cliques.empty():
                cliques.get_nowait()
            estado["painel"] = abrir_painel(root, arquivos, x, y)
        p = estado["painel"]
        if p is not None and not p.fechado:
            gancho.painel_aberto.set()
            while not cliques.empty():
                p.clique_global(*cliques.get_nowait())
        else:
            gancho.painel_aberto.clear()
        root.after(50, tick)

    root.after(50, tick)
    try:
        root.mainloop()
    finally:
        gancho.parar()
        trabalho.put(None)
        trava.close()
    return 0
