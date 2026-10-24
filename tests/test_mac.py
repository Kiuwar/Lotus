"""Versão Mac: lógica pura (qualquer sistema) e integração real (só no CI do Mac)."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import time

import pytest

from conversor import acao_rapida
from conversor.atalho import mac

so_mac = pytest.mark.skipif(sys.platform != "darwin", reason="só no macOS")
# fcntl e caminhos com "/" só existem em sistemas Unix (Mac e Linux).
so_unix = pytest.mark.skipif(sys.platform == "win32", reason="só em sistemas Unix")


# ---------- lógica pura ----------

def test_modifier_flags_mapping():
    mascaras = {"ctrl": 1, "shift": 2, "alt": 4, "win": 8}
    assert mac.mods_de_flags(2 | 4, mascaras) == {"shift", "alt"}
    assert mac.mods_de_flags(0, mascaras) == set()


@pytest.mark.parametrize("tipo,num,esperado", [
    ("esquerdo", 0, "esquerdo"), ("direito", 1, "direito"),
    ("outro", 2, "meio"), ("outro", 3, "lateral1"), ("outro", 4, "lateral2"),
])
def test_mouse_buttons(tipo, num, esperado):
    assert mac.botao_de(tipo, num) == esperado


def test_window_under_point_is_topmost():
    janelas = [
        {"kCGWindowOwnerPID": 10, "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 100, "Height": 100}},
        {"kCGWindowOwnerPID": 20, "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 500, "Height": 500}},
    ]
    assert mac.janela_no_ponto(janelas, 50, 50)["kCGWindowOwnerPID"] == 10
    assert mac.janela_no_ponto(janelas, 300, 300)["kCGWindowOwnerPID"] == 20
    assert mac.janela_no_ponto(janelas, 900, 900) is None


class _R:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_finder_selection_parsing():
    r = mac.ler_selecao_finder(lambda *a, **k: _R(0, "/Users/x/a.pdf\n/Users/x/b c.png\n\n"))
    assert r == ["/Users/x/a.pdf", "/Users/x/b c.png"]


def test_finder_permission_error_explains_fix():
    with pytest.raises(PermissionError, match="Automação"):
        mac.ler_selecao_finder(lambda *a, **k: _R(1, err="execution error: Not authorized (-1743)"))


@so_unix
def test_single_instance_lock_and_stop_signal():
    t1 = mac.travar_instancia()
    assert t1 is not None
    try:
        assert mac.travar_instancia() is None, "segunda instância deve sair"
        assert mac.agente_rodando()
        assert mac.pedir_parada()
        assert mac.parada_pedida() and not mac.parada_pedida()  # consumido
    finally:
        t1.close()
    assert not mac.agente_rodando()


def test_launch_agent_plist():
    d = plistlib.loads(mac.plist_launchd(["/Applications/Lotus.app/Contents/MacOS/Lotus"]))
    assert d["Label"] == "com.kiuwar.lotus.agente" and d["RunAtLoad"] is True
    assert d["ProgramArguments"] == ["/Applications/Lotus.app/Contents/MacOS/Lotus", "--agente"]


def test_mac_defaults_and_names():
    """Roda num processo separado que "é" macOS desde o import (sem recarregar
    módulos no processo dos testes, o que quebraria outros testes)."""
    import json
    from pathlib import Path

    codigo = """
import sys, json
sys.platform = "darwin"
from conversor.atalho import config as c
_, avisos_cmd = c.validar(c.Gatilho(frozenset({"win"}), "mouse", "esquerdo"))
_, avisos_ctrl = c.validar(c.Gatilho(frozenset({"ctrl"}), "mouse", "esquerdo"))
_, avisos_cmd_c = c.validar(c.Gatilho(frozenset({"win"}), "tecla", tecla="C"))
_, avisos_win = c.validar(c.Gatilho(frozenset({"win", "alt"}), "mouse", "meio"))
print(json.dumps({
    "avisos_ctrl": avisos_ctrl, "avisos_cmd_c": avisos_cmd_c, "avisos_win": avisos_win,
    "mods": sorted(c.PADRAO.modificadores),
    "descricao": c.PADRAO.descrever(),
    "avisos_cmd": avisos_cmd,
    "avisos_padrao": c.validar(c.PADRAO)[1],
}))
"""
    raiz = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=raiz, check=True)
    d = json.loads(r.stdout)
    assert d["mods"] == ["alt", "shift"]
    assert d["descricao"] == "⇧ Shift+⌥ Option+clique esquerdo"
    assert any("Finder" in a and "⌘ Cmd" in a for a in d["avisos_cmd"])
    assert d["avisos_padrao"] == [], "o padrão do Mac não pode ter conflito"
    assert any("menu de contexto" in a for a in d["avisos_ctrl"])
    assert any("⌘ Cmd+C" in a for a in d["avisos_cmd_c"])
    assert d["avisos_win"] == [], "no Mac, ⌘ não é reservado como o Win"


# ---------- Ação Rápida ----------

def test_quick_action_bundle_is_valid(tmp_path):
    wf = acao_rapida.gerar(tmp_path, 'echo "$@"')
    info = plistlib.loads((wf / "Contents" / "Info.plist").read_bytes())
    serv = info["NSServices"][0]
    assert serv["NSMenuItem"]["default"] == "Converter com Lotus"
    assert serv["NSMessage"] == "runWorkflowAsService"
    assert serv["NSRequiredContext"] == {"NSApplicationIdentifier": "com.apple.finder"}
    doc = plistlib.loads((wf / "Contents" / "document.wflow").read_bytes())
    params = doc["actions"][0]["action"]["ActionParameters"]
    assert params["COMMAND_STRING"] == 'echo "$@"' and params["inputMethod"] == 1
    assert doc["workflowMetaData"]["serviceInputTypeIdentifier"] == "com.apple.Automator.fileSystemObject"


def test_quick_action_install_uninstall(tmp_path, monkeypatch):
    monkeypatch.setattr(acao_rapida, "pasta_servicos", lambda: tmp_path / "Services")
    assert not acao_rapida.instalada()
    acao_rapida.instalar()
    assert acao_rapida.instalada()
    assert acao_rapida.desinstalar() and not acao_rapida.instalada()
    assert not acao_rapida.desinstalar()


@so_unix
def test_default_command_quotes_paths_with_spaces(monkeypatch, tmp_path):
    app = tmp_path / "Meus Apps" / "Lotus.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(app / "Lotus"))
    cmd = acao_rapida.comando_padrao()
    assert cmd.startswith("open -n -a '") and "Meus Apps/Lotus.app'" in cmd
    assert cmd.endswith('--args --menu-escolher "$@"')


# ---------- só no Mac (CI macos-latest e macos-15-intel) ----------

@so_mac
def test_pyobjc_names_exist():
    import AppKit
    import Quartz

    faltando = [n for n in mac.NOMES_QUARTZ if not hasattr(Quartz, n)]
    assert not faltando, faltando
    for n in ("NSRunningApplication", "NSApplication", "NSApplicationActivationPolicyAccessory"):
        assert hasattr(AppKit, n), n


@so_mac
def test_quick_action_really_runs_with_automator(tmp_path):
    """Executa o workflow gerado pelo Lotus com o Automator do macOS."""
    if not shutil.which("automator"):
        pytest.skip("comando automator ausente")
    marca = tmp_path / "recebido.txt"
    alvo = tmp_path / "contrato.pdf"
    alvo.write_bytes(b"%PDF-1.4\n%%EOF\n")
    wf = acao_rapida.gerar(tmp_path, f'printf "%s\\n" "$@" > "{marca}"')
    r = subprocess.run(["automator", "-i", str(alvo), str(wf)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert marca.read_text().strip().endswith("contrato.pdf"), marca.read_text()


@so_mac
def test_panel_is_transparent_on_mac(tmp_path):
    import tkinter as tk

    from conversor.atalho.painel import Painel
    from conversor.ui import camadas

    from .conftest import make_sample

    root = tk.Tk()
    root.withdraw()
    try:
        p = Painel(root, [str(make_sample("png", tmp_path))], 400, 300)
        root.update()
        assert isinstance(p.superficie, camadas.SuperficieMac), "caiu na reserva (veja o log)"
        assert int(p.top.attributes("-transparent")) == 1
        p.destroy()
    finally:
        root.destroy()


@so_mac
def test_event_tap_without_permission_reports_clearly():
    """No CI não há permissão de Acessibilidade: o gancho deve explicar, não travar."""
    import queue

    g = mac.GanchoMac(mac.config.PADRAO, queue.Queue())
    g.start()
    assert g.pronto.wait(10)
    if g.erro is None:
        g.parar()
        g.join(5)
        pytest.skip("este Mac já tem permissão de Acessibilidade (gancho ativo)")
    assert "Acessibilidade" in g.erro and "Como resolver" in g.erro
    time.sleep(0.1)
