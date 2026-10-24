"""Ícone do Lotus na barra de menus do Mac. O menu é lógica pura (qualquer
sistema); criar o ícone e acionar o menu de verdade só no CI do Mac."""

from __future__ import annotations

import queue
import sys

import pytest

from conversor.atalho import barra_mac as bm
from conversor.atalho import controle

so_mac = pytest.mark.skipif(sys.platform != "darwin", reason="só no macOS")


def test_menu_items_and_checkmark():
    itens = bm.itens_menu(True, "⌥ Option + ⇧ Shift + clique")
    comandos = [c for c, _, _ in itens if c]
    assert comandos == [bm.CONVERTER, bm.ABRIR, bm.ATALHO, bm.ATIVAR, bm.AJUDA, bm.SAIR]
    marcados = [c for c, _, m in itens if m]
    assert marcados == [bm.ATALHO]
    assert not [c for c, _, m in bm.itens_menu(False, "x") if m]


def test_icon_wording_follows_the_system(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert controle.onde_icone() == "na barra de menus"
    monkeypatch.setattr(sys, "platform", "win32")
    assert controle.onde_icone() == "ao lado do relógio"


@so_mac
def test_appkit_names_exist():
    import AppKit

    faltando = [n for n in bm.NOMES_BARRA if not hasattr(AppKit, n)]
    assert not faltando, faltando


@so_mac
def test_real_menu_bar_item_only_queues_commands():
    from conversor.ui.icone import RECURSOS

    fila: queue.Queue = queue.Queue()
    barra = bm.BarraMac(fila, str(RECURSOS / "lotus.png"), False, "⌥ Option + ⇧ Shift + clique")
    try:
        for cmd in (bm.ABRIR, bm.CONVERTER):
            i = barra.menu.indexOfItem_(barra._itens[cmd])
            barra.menu.performActionForItemAtIndex_(i)
            assert fila.get_nowait() == cmd
        barra.atualizar(True, "x")
        from AppKit import NSControlStateValueOn

        assert barra._itens[bm.ATALHO].state() == NSControlStateValueOn
    finally:
        barra.remover()
