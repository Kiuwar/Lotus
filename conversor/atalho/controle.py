"""Liga/desliga o agente do atalho e o início automático com o Windows.

Início automático: valor "Lotus.Atalho" em
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (por usuário, sem
administrador). Nenhum outro valor dessa chave é tocado.
"""

from __future__ import annotations

import subprocess
import sys
import time

from conversor import shell
from conversor.atalho import config
from conversor.logs import get_logger

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALOR = "Lotus.Atalho"


def comando_agente() -> str:
    return " ".join(f'"{p}"' for p in shell.launcher_command()) + " --agente"


def _wr(mod=None):
    if mod is not None:
        return mod
    import winreg

    return winreg


def _mac(winreg_module) -> bool:
    return winreg_module is None and sys.platform == "darwin"


def ativar_inicio(winreg_module=None) -> None:
    if _mac(winreg_module):  # LaunchAgent do usuário
        from conversor.atalho import mac

        mac.arquivo_launchd().parent.mkdir(parents=True, exist_ok=True)
        mac.arquivo_launchd().write_bytes(mac.plist_launchd(shell.launcher_command()))
        return
    wr = _wr(winreg_module)
    with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_WRITE) as k:
        wr.SetValueEx(k, VALOR, 0, wr.REG_SZ, comando_agente())


def desativar_inicio(winreg_module=None) -> None:
    if _mac(winreg_module):
        from conversor.atalho import mac

        mac.arquivo_launchd().unlink(missing_ok=True)
        return
    wr = _wr(winreg_module)
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, VALOR)
    except FileNotFoundError:
        pass


def inicio_registrado(winreg_module=None) -> str | None:
    if _mac(winreg_module):
        import plistlib

        from conversor.atalho import mac

        try:
            d = plistlib.loads(mac.arquivo_launchd().read_bytes())
        except (OSError, plistlib.InvalidFileException):
            return None
        return " ".join(f'"{a}"' for a in d["ProgramArguments"][:-1]) + " --agente"
    wr = _wr(winreg_module)
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY) as k:
            return wr.QueryValueEx(k, VALOR)[0]
    except FileNotFoundError:
        return None


def agente_rodando() -> bool:
    if sys.platform == "darwin":
        from conversor.atalho import mac

        return mac.agente_rodando()
    if sys.platform != "win32":
        return False
    from conversor.atalho import winapi

    return winapi.agente_rodando()


def iniciar_agente(espera: float = 5.0) -> bool:
    if sys.platform not in ("win32", "darwin"):
        return False
    if agente_rodando():
        return True
    cmd = shell.launcher_command() + ["--agente"]
    try:
        if sys.platform == "darwin":
            subprocess.Popen(cmd, start_new_session=True, close_fds=True)
        else:
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    except OSError:
        # Ex.: Lotus.exe movido ou apagado. Quem chamou informa "não iniciou".
        get_logger().exception("não foi possível iniciar o agente: %r", cmd)
        return False
    fim = time.time() + espera
    while time.time() < fim:
        if agente_rodando():
            return True
        time.sleep(0.1)
    return False


def parar_agente(espera: float = 5.0) -> bool:
    if sys.platform == "darwin":
        from conversor.atalho import mac as alvo
    elif sys.platform == "win32":
        from conversor.atalho import winapi as alvo
    else:
        return True
    if not alvo.agente_rodando():
        return True
    alvo.pedir_parada()
    fim = time.time() + espera
    while time.time() < fim:
        if not alvo.agente_rodando():
            return True
        time.sleep(0.1)
    return False


def ativar(winreg_module=None) -> str:
    cfg = config.carregar()
    cfg.atalho_ativo = True
    config.salvar(cfg)
    ativar_inicio(winreg_module)
    ok = iniciar_agente()
    estado = "ligado" if ok else "configurado, mas o agente não iniciou (veja o log)"
    onde = "no Finder ou na Mesa" if sys.platform == "darwin" else "no Explorer ou na área de trabalho"
    return f"Painel flutuante {estado}: {cfg.gatilho.descrever()} {onde}."


def desativar(winreg_module=None) -> str:
    cfg = config.carregar()
    cfg.atalho_ativo = False
    config.salvar(cfg)
    desativar_inicio(winreg_module)
    parar_agente()
    return "Painel flutuante desligado."
