"""Ajuda: conteúdo certo para cada sistema e janela que abre sem internet."""

from __future__ import annotations

import gc

import pytest

from conversor import ajuda
from conversor.core import registry


def _texto(sistema):
    return "\n".join(t for _, blocos in ajuda.secoes(sistema) for _, t in blocos)


def test_windows_help_talks_about_explorer_and_right_click():
    t = _texto("win32")
    assert "Ctrl + Shift + clique" in t and "Mostrar mais opções" in t
    assert "Finder" not in t and "⌥" not in t


def test_mac_help_talks_about_finder_permissions_and_quick_action():
    t = _texto("darwin")
    assert "⌥ Option + ⇧ Shift + clique" in t and "Converter com Lotus" in t
    assert "Ativar o painel no Mac" in t and "Explorer" not in t


def test_format_count_comes_from_the_registry():
    total = len(registry.all_converters())
    assert f"faz {total} conversões" in _texto("win32")


@pytest.mark.parametrize("sistema", ["win32", "darwin"])
def test_privacy_section_mentions_the_only_network_use(sistema):
    nomes = [n for n, _ in ajuda.secoes(sistema)]
    assert "Privacidade" in nomes
    priv = dict(ajuda.secoes(sistema))["Privacidade"]
    assert any("Procurar atualização" in t and "IP" in t for _, t in priv)


tk = pytest.importorskip("tkinter")


def test_help_window_has_tabs_and_action_buttons():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    root.withdraw()
    chamou = []
    try:
        from conversor.ui.janela_ajuda import JanelaAjuda

        j = JanelaAjuda(root, acoes={"Diagnosticar e reparar": lambda: chamou.append(1)}, sistema="win32")
        root.update()
        assert [j.abas.tab(i, "text") for i in j.abas.tabs()][:2] == ["Começar", "Formatos"]
        assert "Adicionar arquivos" in j.textos["Começar"].get("1.0", "end")
        assert j.rodape.winfo_ismapped(), "rodapé com os botões visível"
        botao = next(w for w in j.rodape.winfo_children()
                     if w.cget("text") == "Diagnosticar e reparar")
        botao.invoke()
        assert chamou == [1]
        j.destroy()
    finally:
        root.destroy()
        gc.collect()
