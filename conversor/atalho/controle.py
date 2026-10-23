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

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALOR = "Lotus.Atalho"


def comando_agente() -> str:
    return " ".join(f'"{p}"' for p in shell.launcher_command()) + " --agente"


def _wr(mod=None):
    if mod is not None:
        return mod
    import winreg

    return winreg


def ativar_inicio(winreg_module=None) -> None:
    wr = _wr(winreg_module)
    with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_WRITE) as k:
        wr.SetValueEx(k, VALOR, 0, wr.REG_SZ, comando_agente())


def desativar_inicio(winreg_module=None) -> None:
    wr = _wr(winreg_module)
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, VALOR)
    except FileNotFoundError:
        pass


def inicio_registrado(winreg_module=None) -> str | None:
    wr = _wr(winreg_module)
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY) as k:
            return wr.QueryValueEx(k, VALOR)[0]
    except FileNotFoundError:
        return None


def agente_rodando() -> bool:
    if sys.platform != "win32":
        return False
    from conversor.atalho import winapi

    return winapi.agente_rodando()


def iniciar_agente(espera: float = 5.0) -> bool:
    if sys.platform != "win32":
        return False
    if agente_rodando():
        return True
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(shell.launcher_command() + ["--agente"], creationflags=flags, close_fds=True)
    fim = time.time() + espera
    while time.time() < fim:
        if agente_rodando():
            return True
        time.sleep(0.1)
    return False


def parar_agente(espera: float = 5.0) -> bool:
    if sys.platform != "win32":
        return True
    from conversor.atalho import winapi

    if not winapi.agente_rodando():
        return True
    winapi.pedir_parada()
    fim = time.time() + espera
    while time.time() < fim:
        if not winapi.agente_rodando():
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
    return f"Painel flutuante {estado}: {cfg.gatilho.descrever()} numa janela do Explorer."


def desativar(winreg_module=None) -> str:
    cfg = config.carregar()
    cfg.atalho_ativo = False
    config.salvar(cfg)
    desativar_inicio(winreg_module)
    parar_agente()
    return "Painel flutuante desligado."
