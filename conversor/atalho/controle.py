"""Liga/desliga o agente (atalho + ícone ao lado do relógio) e o início automático.

O agente roda se o atalho do painel OU o ícone da bandeja estiver ligado
(`precisa_rodar`); o gancho de mouse só é instalado com o atalho ligado.

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


# Ícone do Lotus: ao lado do relógio (Windows, bandeja.py) ou na barra de
# menus (Mac, barra_mac.py). A configuração é a mesma (`cfg.bandeja`).
BANDEJA_SUPORTADA = sys.platform in ("win32", "darwin")


def onde_icone() -> str:
    return "na barra de menus" if sys.platform == "darwin" else "ao lado do relógio"


def precisa_rodar(cfg: config.Config) -> bool:
    return cfg.atalho_ativo or (cfg.bandeja and BANDEJA_SUPORTADA)


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
    if precisa_rodar(cfg):
        # O agente segue rodando pelo ícone; ele relê a configuração e tira o gancho.
        return f"Painel flutuante desligado (o Lotus continua {onde_icone()})."
    desativar_inicio(winreg_module)
    parar_agente()
    return "Painel flutuante desligado."


def alternar_atalho() -> config.Config:
    """Menu do ícone: liga/desliga o painel por atalho (o agente aplica na hora)."""
    cfg = config.carregar()
    cfg.atalho_ativo = not cfg.atalho_ativo
    config.salvar(cfg)
    return cfg


def ativar_bandeja(winreg_module=None) -> str:
    cfg = config.carregar()
    cfg.bandeja = True
    config.salvar(cfg)
    if not BANDEJA_SUPORTADA:
        return "O ícone do Lotus existe só no Windows e no Mac."
    ativar_inicio(winreg_module)
    ok = iniciar_agente()
    return f"Lotus {onde_icone()}: " + ("ligado." if ok else "configurado, mas não iniciou (veja o log).")


def desativar_bandeja(winreg_module=None) -> str:
    cfg = config.carregar()
    cfg.bandeja = False
    config.salvar(cfg)
    if precisa_rodar(cfg):
        return f"Ícone {onde_icone()} desligado (o painel por atalho continua ligado)."
    desativar_inicio(winreg_module)
    parar_agente()
    return f"Ícone {onde_icone()} desligado."
