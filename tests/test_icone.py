"""Ícone da flor de lótus: arquivos gerados, atualizados e aplicados nas janelas."""

from __future__ import annotations

import sys

import pytest
from PIL import Image, ImageChops

from conversor.ui import icone


def test_icon_files_exist_with_all_windows_sizes():
    ico = Image.open(icone.RECURSOS / "lotus.ico")
    assert sorted(ico.info["sizes"]) == [(t, t) for t in icone.TAMANHOS_ICO]
    assert Image.open(icone.RECURSOS / "lotus.icns").size == (1024, 1024)
    assert Image.open(icone.RECURSOS / "lotus.png").size == (512, 512)


def test_committed_icons_match_the_drawing(tmp_path):
    """Mudou o desenho em icone.py? Rode scripts/gerar_icone.py."""
    novos = icone.gerar(tmp_path)
    a, b = Image.open(icone.RECURSOS / "lotus.png"), Image.open(novos["png"])
    assert ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox() is None
    salvo, gerado = Image.open(icone.RECURSOS / "lotus.ico"), Image.open(novos["ico"])
    for t in icone.TAMANHOS_ICO:
        salvo.size = gerado.size = (t, t)
        diff = ImageChops.difference(salvo.copy().convert("RGBA"), gerado.copy().convert("RGBA"))
        assert diff.getbbox() is None, f"lotus.ico {t}px desatualizado"


@pytest.mark.parametrize("tamanho", [16, 32, 256])
def test_flower_is_visible_and_corners_transparent(tamanho):
    img = icone.desenhar_lotus(tamanho)
    assert img.getpixel((0, 0))[3] == 0, "canto deve ser transparente"
    cobertos = sum(img.getchannel("A").histogram()[129:])
    assert cobertos > tamanho * tamanho * 0.25, "a flor precisa ocupar boa parte do ícone"
    # rosa/lilás presente (não é um borrão cinza)
    r, g, b, _ = img.getpixel((tamanho // 2, int(tamanho * 0.55)))
    assert r > g and b > g


def test_icon_is_applied_to_tk_window():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    try:
        icone.aplicar_icone(root)
        if sys.platform != "win32":
            assert root._lotus_icone.width() == 512
    finally:
        root.destroy()
