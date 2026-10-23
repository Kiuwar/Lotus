"""Atalho do painel flutuante: configuração, detecção do gesto, controle e janelas."""

from __future__ import annotations

import gc
import json

import pytest

from conversor.atalho import config, controle, gesto
from conversor.atalho.config import Gatilho

from .fake_winreg import FakeWinreg

CTRL_SHIFT = frozenset({"ctrl", "shift"})


# ---------- configuração ----------

def test_default_is_ctrl_shift_left_click():
    assert config.PADRAO.descrever() == "Ctrl+Shift+clique esquerdo"
    assert config.validar(config.PADRAO) == ([], [])


@pytest.mark.parametrize(
    "g",
    [
        Gatilho(frozenset(), "mouse", "esquerdo"),
        Gatilho(frozenset(), "mouse", "direito"),
        Gatilho(frozenset(), "tecla", tecla="C"),
        Gatilho(frozenset({"ctrl"}), "tecla", tecla="?"),
        Gatilho(frozenset({"hyper"}), "mouse"),
        Gatilho(CTRL_SHIFT, "teclado"),
    ],
)
def test_dangerous_or_invalid_triggers_are_rejected(g):
    erros, _ = config.validar(g)
    assert erros


@pytest.mark.parametrize(
    "g,aviso",
    [
        (Gatilho(frozenset({"ctrl"}), "mouse", "esquerdo"), "selecionar vários"),
        (Gatilho(frozenset({"ctrl"}), "tecla", tecla="C"), "Ctrl+C"),
        (Gatilho(frozenset({"win", "alt"}), "mouse", "meio"), "Win"),
    ],
)
def test_conflicting_triggers_warn_but_are_allowed(g, aviso):
    erros, avisos = config.validar(g)
    assert not erros and any(aviso in a for a in avisos)


def test_any_mouse_button_and_function_key_are_accepted():
    for b in config.BOTOES:
        assert not config.validar(Gatilho(frozenset({"alt"}), "mouse", b))[0]
    assert not config.validar(Gatilho(frozenset(), "mouse", "meio"))[0]  # meio sozinho: ok
    assert not config.validar(Gatilho(frozenset(), "tecla", tecla="F9"))[0]


def test_vk_codes():
    assert config.vk_da_tecla("A") == 0x41
    assert config.vk_da_tecla("7") == 0x37
    assert config.vk_da_tecla("F1") == 0x70
    assert config.vk_da_tecla("F24") == 0x87
    with pytest.raises(ValueError):
        config.vk_da_tecla("F25")


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    g = Gatilho(frozenset({"alt", "win"}), "tecla", tecla="F8")
    config.salvar(config.Config(g, atalho_ativo=True), p)
    c = config.carregar(p)
    assert c.gatilho == g and c.atalho_ativo is True
    assert json.loads(p.read_text(encoding="utf-8"))["atalho"]["modificadores"] == ["alt", "win"]


def test_saving_invalid_trigger_is_refused(tmp_path):
    with pytest.raises(ValueError):
        config.salvar(config.Config(Gatilho(frozenset(), "mouse", "esquerdo")), tmp_path / "c.json")
    assert not (tmp_path / "c.json").exists()


@pytest.mark.parametrize("conteudo", ["{quebrado", '{"atalho": {"modificadores": [], "tipo": "mouse"}}'])
def test_corrupt_or_dangerous_config_is_repaired(tmp_path, conteudo):
    p = tmp_path / "config.json"
    p.write_text(conteudo, encoding="utf-8")
    c = config.carregar(p)
    assert c.gatilho == config.PADRAO
    assert (tmp_path / "config.json.corrompido").read_text(encoding="utf-8") == conteudo


# ---------- detecção do gesto ----------

def _det(g=config.PADRAO):
    return gesto.Detector(g)


def test_gesture_fires_and_swallows_matching_release():
    d = _det()
    assert d.evento("esquerdo", True, {"ctrl", "shift"}, False, "CabinetWClass") == gesto.DISPARAR
    assert d.evento("esquerdo", False, set(), False, "CabinetWClass") == gesto.ENGOLIR
    assert d.evento("esquerdo", False, set(), False, "CabinetWClass") == gesto.PASSAR


@pytest.mark.parametrize(
    "botao,mods,injetado,classe",
    [
        ("esquerdo", {"ctrl"}, False, "CabinetWClass"),  # falta Shift
        ("esquerdo", {"ctrl", "shift", "alt"}, False, "CabinetWClass"),  # tecla a mais
        ("direito", {"ctrl", "shift"}, False, "CabinetWClass"),  # outro botão
        ("esquerdo", {"ctrl", "shift"}, True, "CabinetWClass"),  # clique simulado
        ("esquerdo", {"ctrl", "shift"}, False, "Chrome_WidgetWin_1"),  # fora do Explorer
        ("esquerdo", {"ctrl", "shift"}, False, "Progman"),  # área de trabalho
    ],
)
def test_gesture_passes_through_otherwise(botao, mods, injetado, classe):
    d = _det()
    assert d.evento(botao, True, mods, injetado, classe) == gesto.PASSAR
    assert d.evento(botao, False, set(), injetado, classe) == gesto.PASSAR


def test_keyboard_trigger_never_fires_from_mouse():
    d = _det(Gatilho(CTRL_SHIFT, "tecla", tecla="K"))
    assert d.evento("esquerdo", True, {"ctrl", "shift"}, False, "CabinetWClass") == gesto.PASSAR


def test_choose_tab_uses_the_one_that_changed():
    antes = {0: ["C:/a.txt"], 1: ["C:/x.png", "C:/y.png"]}
    depois = {0: ["C:/a.txt"], 1: ["C:/z.png"]}
    assert gesto.escolher_aba(antes, depois) == ["C:/z.png"]


def test_choose_tab_unchanged_single_selection():
    assert gesto.escolher_aba({0: ["C:/a.txt"]}, {0: ["C:/a.txt"]}) == ["C:/a.txt"]
    assert gesto.escolher_aba({0: ["a"], 1: ["b"]}, {0: ["a"], 1: ["b"]}) == []  # ambíguo: nada
    assert gesto.escolher_aba({0: []}, {0: []}) == []


# ---------- início automático e reparo ----------

def test_autostart_roundtrip_with_fake_registry(monkeypatch):
    monkeypatch.setattr(controle.shell, "launcher_command", lambda: [r"C:\L\Lotus.exe"])
    wr = FakeWinreg()
    run = r"software\microsoft\windows\currentversion\run"
    wr.CreateKeyEx(wr.HKEY_CURRENT_USER, controle.RUN_KEY)
    wr.keys[run]["OutroPrograma"] = "outro.exe"
    controle.ativar_inicio(wr)
    assert controle.inicio_registrado(wr) == r'"C:\L\Lotus.exe" --agente'
    controle.desativar_inicio(wr)
    assert controle.inicio_registrado(wr) is None
    assert wr.keys[run] == {"OutroPrograma": "outro.exe"}  # nada de outro programa é tocado
    controle.desativar_inicio(wr)  # repetir não dá erro


def test_diagnostics_repairs_stale_autostart(monkeypatch):
    from conversor import diagnostics

    # Não iniciar um processo de verdade (no Windows isso tentaria abrir o .exe).
    monkeypatch.setattr(controle, "agente_rodando", lambda: False)
    monkeypatch.setattr(controle, "iniciar_agente", lambda: False)
    wr = FakeWinreg()
    monkeypatch.setattr(controle.shell, "launcher_command", lambda: [r"D:\velho\Lotus.exe"])
    controle.ativar_inicio(wr)
    config.salvar(config.Config(config.PADRAO, atalho_ativo=True))
    monkeypatch.setattr(controle.shell, "launcher_command", lambda: [r"E:\novo\Lotus.exe"])
    msg = diagnostics.repair_autostart(wr)
    assert "reparado" in msg and "NÃO está rodando" in msg
    assert controle.inicio_registrado(wr) == r'"E:\novo\Lotus.exe" --agente'


def test_diagnostics_removes_leftover_autostart_when_off(monkeypatch):
    from conversor import diagnostics

    wr = FakeWinreg()
    controle.ativar_inicio(wr)
    config.salvar(config.Config(config.PADRAO, atalho_ativo=False))
    assert "removido" in diagnostics.repair_autostart(wr)
    assert controle.inicio_registrado(wr) is None


# ---------- janelas (display virtual) ----------

tk = pytest.importorskip("tkinter")


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("sem display disponível")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass
    gc.collect()


def test_panel_position_stays_on_screen():
    from conversor.atalho.painel import posicao_na_tela

    assert posicao_na_tela(100, 100, 300, 200, 1920, 1080) == (112, 112)
    assert posicao_na_tela(1900, 1070, 300, 200, 1920, 1080) == (1588, 858)
    assert posicao_na_tela(5, 5, 3000, 2000, 1920, 1080) == (0, 0)


def test_floating_panel_shows_formats_and_converts(root, sample):
    from conversor.atalho.painel import abrir_painel

    src = sample("png")
    top = abrir_painel(root, [str(src)], 50, 50)
    root.update()
    chooser = next(w for w in top.winfo_children()[0].winfo_children())
    assert "pdf" in chooser.buttons and top.overrideredirect()
    chooser.buttons["pdf"].invoke()
    import time

    fim = time.time() + 20
    while not (chooser.worker and not chooser.worker.is_alive() and chooser.outcomes):
        root.update()
        assert time.time() < fim
        time.sleep(0.05)
        if chooser.worker and not chooser.worker.is_alive():
            root.update()
    assert (src.parent / "amostra.pdf").is_file()
    top.destroy()


def test_config_window_blocks_dangerous_and_saves(root, monkeypatch):
    from conversor.atalho.janela_config import JanelaAtalho

    # No Windows, salvar liga/desliga o agente de verdade: aqui só a configuração importa.
    monkeypatch.setattr(controle, "ativar", lambda: "ativado")
    monkeypatch.setattr(controle, "desativar", lambda: "desativado")

    j = JanelaAtalho(root)
    assert j.gatilho() == config.PADRAO
    for v in j.mods.values():
        v.set(False)
    j.atualizar()
    assert str(j.salvar_btn["state"]) == "disabled"  # clique esquerdo puro: proibido

    j.mods["alt"].set(True)
    j.tipo.set("tecla")
    j.tecla.set("F7")
    j.atualizar()
    assert str(j.salvar_btn["state"]) == "normal"
    assert j.resumo["text"] == "Atalho: Alt+F7"
    j.salvar()
    assert config.carregar().gatilho == Gatilho(frozenset({"alt"}), "tecla", tecla="F7")
    config.salvar(config.Config())  # volta ao padrão para os outros testes


def test_launcher_silent_mode_shows_nothing(monkeypatch):
    from conversor import launcher

    shown = []
    monkeypatch.setattr(launcher, "_silencioso", False)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: shown.append(a))
    monkeypatch.setattr("conversor.diagnostics.run", lambda: ["ok"])
    assert launcher.main(["--reparar", "--silencioso"]) == 0
    assert shown == []


def test_start_agent_with_missing_exe_reports_failure(monkeypatch):
    """Lotus.exe apagado/movido: diagnóstico não pode travar."""
    import subprocess
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(controle, "agente_rodando", lambda: False)
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 0x8, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)

    def sem_arquivo(*a, **k):
        raise FileNotFoundError(2, "O sistema não pode encontrar o arquivo especificado")

    monkeypatch.setattr(subprocess, "Popen", sem_arquivo)
    assert controle.iniciar_agente(espera=0.1) is False
