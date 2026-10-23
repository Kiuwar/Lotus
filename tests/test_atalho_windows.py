"""Camada nativa do atalho: só roda no Windows (CI windows-latest).

Cobre o que o Linux não consegue verificar: tamanhos das estruturas da API,
gancho de mouse, tecla de atalho, instância única, parada do agente e a
leitura da seleção de uma janela real do Explorer.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="API do Windows")

ROOT = Path(__file__).resolve().parent.parent


def test_struct_sizes_match_windows_sdk():
    from conversor.atalho import winapi

    assert ctypes.sizeof(winapi.INPUT) == 40  # x64: 4 + 4 (alinhamento) + 32
    assert ctypes.sizeof(winapi.MSLLHOOKSTRUCT) == 32
    assert ctypes.sizeof(winapi.KEYBDINPUT) == 24
    assert ctypes.sizeof(winapi.MOUSEINPUT) == 32


def test_hotkey_register_and_unregister():
    from conversor.atalho import winapi

    flags = winapi.MOD_CONTROL | winapi.MOD_SHIFT | winapi.MOD_ALT | winapi.MOD_NOREPEAT
    assert winapi.user32.RegisterHotKey(None, 0x7777, flags, 0x7B)  # Ctrl+Shift+Alt+F12
    assert winapi.user32.UnregisterHotKey(None, 0x7777)


def test_mouse_hook_installs_and_stops():
    from queue import Queue

    from conversor.atalho import agente, config

    g = agente.Gancho(config.PADRAO, Queue())
    g.start()
    assert g.pronto.wait(5)
    assert g.erro is None, g.erro
    assert g._hook
    g.parar()
    g.join(5)
    assert not g.is_alive()


def test_hotkey_trigger_registers_in_hook_thread():
    from queue import Queue

    from conversor.atalho import agente, config

    gat = config.Gatilho(frozenset({"ctrl", "shift", "alt"}), "tecla", tecla="F11")
    g = agente.Gancho(gat, Queue())
    g.start()
    assert g.pronto.wait(5)
    assert g.erro is None, g.erro
    g.parar()
    g.join(5)


def test_agent_single_instance_and_stop(tmp_path):
    from conversor.atalho import winapi

    env = dict(os.environ, APPDATA=str(tmp_path), LOCALAPPDATA=str(tmp_path))
    cmd = [sys.executable, str(ROOT / "packaging" / "app_gui.py"), "--agente"]
    p1 = subprocess.Popen(cmd, env=env)
    try:
        fim = time.time() + 20
        while not winapi.agente_rodando():
            assert p1.poll() is None, f"agente saiu com código {p1.returncode}"
            assert time.time() < fim, "agente não iniciou"
            time.sleep(0.2)
        p2 = subprocess.run(cmd, env=env, timeout=20)  # segunda instância sai sozinha
        assert p2.returncode == 0
        assert p1.poll() is None, "a primeira instância não pode cair"
        assert winapi.pedir_parada()
        assert p1.wait(15) == 0
        assert not winapi.agente_rodando()
    finally:
        if p1.poll() is None:
            p1.kill()


def test_explorer_selection_is_read(tmp_path):
    """Abre o Explorer com um arquivo selecionado e lê a seleção pelo COM."""
    import win32com.client

    from conversor.atalho import selecao

    alvo = tmp_path / "selecionado.txt"
    alvo.write_text("oi", encoding="utf-8")
    subprocess.Popen(["explorer", f"/select,{alvo}"])
    selecao.iniciar_com()
    shell = win32com.client.Dispatch("Shell.Application")
    achado, janela = None, None
    fim = time.time() + 30
    while time.time() < fim and achado is None:
        jans = shell.Windows()
        for i in range(jans.Count):
            try:
                j = jans.Item(i)
                if j is None:
                    continue
                sel = selecao.selecoes(int(j.HWND))
                if any(str(alvo).lower() in (p.lower() for p in v) for v in sel.values()):
                    achado, janela = sel, j
            except Exception:
                continue
        time.sleep(0.5)
    if achado is None:
        pytest.skip("o Explorer não abriu uma janela visível neste runner")
    try:
        assert selecao.apenas_arquivos([str(alvo), str(tmp_path)]) == [str(alvo)]
    finally:
        janela.Quit()


def test_real_autostart_roundtrip(monkeypatch):
    import winreg

    from conversor.atalho import controle

    monkeypatch.setattr(controle, "RUN_KEY", r"Software\LotusTeste\Run")  # não mexe no Run real
    try:
        controle.ativar_inicio()
        assert controle.inicio_registrado().endswith("--agente")
        controle.desativar_inicio()
        assert controle.inicio_registrado() is None
    finally:
        from conversor import shell

        shell._delete_tree(winreg, winreg.HKEY_CURRENT_USER, r"Software\LotusTeste")


def test_injected_click_is_ignored_by_detector():
    """O clique simulado pelo próprio Lotus chega ao gancho marcado como injetado."""
    from queue import Queue

    from conversor.atalho import agente, config, gesto, winapi

    vistos = []

    class Espiao(gesto.Detector):
        def evento(self, botao, apertou, mods, injetado, classe):
            vistos.append((botao, apertou, injetado))
            return gesto.PASSAR

    g = agente.Gancho(config.PADRAO, Queue())
    g.detector = Espiao(config.PADRAO)
    g.start()
    assert g.pronto.wait(5)
    try:
        # Clique num ponto neutro (canto da área de trabalho), fora do Explorer.
        winapi.user32.SetCursorPos(1, 1)
        winapi.soltar_modificadores_e_clicar(set())
        fim = time.time() + 5
        while len(vistos) < 2 and time.time() < fim:
            time.sleep(0.05)
    finally:
        g.parar()
        g.join(5)
    if not vistos:
        pytest.skip("este runner não entrega eventos de mouse simulados ao gancho")
    assert ("esquerdo", True, True) in vistos and ("esquerdo", False, True) in vistos


def test_threads_do_not_leak_after_stop():
    from queue import Queue

    from conversor.atalho import agente, config

    antes = threading.active_count()
    g = agente.Gancho(config.PADRAO, Queue())
    g.start()
    g.pronto.wait(5)
    g.parar()
    g.join(5)
    assert threading.active_count() == antes
