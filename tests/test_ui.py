"""Base visual: temas, grupos, geometria do painel e desenho (pixels)."""

from __future__ import annotations

import itertools
import math

import pytest
from PIL import Image

from conversor.core import registry
from conversor.ui import grupos, radial, render, tema

ORIGENS = sorted({c.source for c in registry.all_converters()})


# ---------- temas ----------

@pytest.mark.parametrize("nome", list(tema.PRESETS))
@pytest.mark.parametrize("escuro", [False, True])
def test_every_theme_text_is_readable(nome, escuro):
    p = tema.paleta(tema.Aparencia(tema=nome), escuro=escuro)
    assert tema.contraste(p.texto, p.fundo) >= 4.5
    assert tema.contraste(p.texto, p.superficie) >= 4.5
    for cor in p.grupos.values():
        assert tema.contraste(tema.legivel(cor, p.fundo), p.fundo) >= 4.5
        # texto sobre a caixa destacada (cor cheia do grupo)
        assert tema.contraste(tema.texto_sobre(cor), cor) >= 3.0


def test_custom_colors_override_theme():
    a = tema.Aparencia(destaque="#123456", fundo="#ABCDEF", cores_grupo={"Imagem": "#00FF00"})
    p = tema.paleta(a, escuro=False)
    assert p.destaque == "#123456" and p.fundo == "#ABCDEF" and p.grupos["Imagem"] == "#00FF00"


@pytest.mark.parametrize("campo,valor", [
    ("tema", "Neon"), ("modo", "noite"), ("tamanho", "XG"), ("forma", "estrela"),
    ("opacidade", 0.2), ("destaque", "azul"), ("cores_grupo", {"Imagem": "#12"}),
    ("cores_grupo", {"Planilha": "#123456"}),
])
def test_invalid_appearance_is_rejected(campo, valor):
    assert tema.validar(tema.Aparencia(**{campo: valor}))


def test_appearance_roundtrip_and_repair(tmp_path):
    p = tmp_path / "aparencia.json"
    a = tema.Aparencia(tema="Verde", modo="escuro", destaque="#FF0000", opacidade=0.8, tamanho="G", forma="cartao")
    tema.salvar(a, p)
    assert tema.carregar(p) == a
    p.write_text('{"tema": "Neon"}', encoding="utf-8")
    assert tema.carregar(p) == tema.PADRAO
    assert (tmp_path / "aparencia.json.corrompido").exists()


def test_fixed_mode_ignores_system(monkeypatch):
    monkeypatch.setattr(tema, "sistema_escuro", lambda: True)
    assert tema.paleta(tema.Aparencia(modo="claro")).escuro is False
    assert tema.paleta(tema.Aparencia(modo="auto")).escuro is True


# ---------- grupos ----------

def test_every_target_format_has_a_known_group():
    destinos = {c.target for c in registry.all_converters()}
    assert destinos <= set(grupos.FAMILIA), destinos - set(grupos.FAMILIA)


def test_pdf_targets_are_split_by_family():
    g = dict(grupos.agrupar(["png", "jpg", "txt", "docx"]))
    assert g == {"Imagem": ["png", "jpg"], "Documento": ["docx"], "Texto e dados": ["txt"]}


# ---------- geometria ----------

def _sobrepostos(lay):
    return [(a.fmt, b.fmt) for a, b in itertools.combinations(lay.itens, 2)
            if abs(a.x - b.x) < (a.w + b.w) / 2 and abs(a.y - b.y) < (a.h + b.h) / 2]


@pytest.mark.parametrize("origem", ORIGENS)
@pytest.mark.parametrize("forma", ["radial", "cartao"])
@pytest.mark.parametrize("escala", [0.8, 1.0, 1.25])
def test_layout_has_no_overlap_and_fits(origem, forma, escala):
    g = grupos.agrupar(registry.targets_for(origem, only_available=False))
    lay = radial.montar(g, forma, escala)
    assert not _sobrepostos(lay)
    for it in lay.itens:
        assert it.x - it.w / 2 >= 0 and it.y - it.h / 2 >= 0
        assert it.x + it.w / 2 <= lay.largura and it.y + it.h / 2 <= lay.altura
        if forma == "radial":
            # nenhuma caixa encosta no círculo do arquivo nem sai do disco
            d = math.hypot(it.x - lay.ancora_x, it.y - lay.ancora_y)
            assert d - math.hypot(it.w, it.h) / 2 > lay.centro_r
            assert d + math.hypot(it.w, it.h) / 2 < lay.fundo_r
    total = len(registry.targets_for(origem, only_available=False))
    mostrados = [i.fmt for i in lay.itens if i.fmt != radial.MAIS]
    if total > radial.MAX_ITENS:
        assert len(lay.itens) == radial.MAX_ITENS and lay.itens[-1].fmt == radial.MAIS
    else:
        assert len(mostrados) == total


def test_groups_are_contiguous_and_separated():
    g = grupos.agrupar(["png", "jpg", "docx", "txt"])
    lay = radial.radial(g)
    ordem = [i.grupo for i in lay.itens]
    assert ordem == ["Imagem", "Imagem", "Documento", "Texto e dados"]
    assert [f.grupo for f in lay.faixas] == ["Imagem", "Documento", "Texto e dados"]
    for a, b in zip(lay.faixas, lay.faixas[1:]):
        assert b.ang_ini > a.ang_fim, "deve haver espaço entre grupos"


def test_hit_test():
    lay = radial.radial(grupos.agrupar(["png", "txt"]))
    it = lay.itens[0]
    assert lay.hit_test(it.x, it.y) == "png"
    assert lay.hit_test(lay.ancora_x, lay.ancora_y) == radial.CENTRO
    assert lay.hit_test(1, 1) is None


def test_more_button_when_too_many_formats():
    muitos = [f"f{i}" for i in range(20)]
    lay = radial.radial([("Imagem", muitos)])
    assert len(lay.itens) == radial.MAX_ITENS and lay.itens[-1].fmt == radial.MAIS


@pytest.mark.parametrize("cursor", [(5, 5), (1915, 1075), (960, 540), (0, 1079)])
def test_panel_stays_on_screen(cursor):
    lay = radial.radial(grupos.agrupar(["png", "jpg", "txt", "docx"]))
    x, y = radial.posicionar(lay, *cursor, 1920, 1080)
    assert 0 <= x <= 1920 - lay.largura and 0 <= y <= 1080 - lay.altura


def test_radial_is_centered_on_cursor_when_there_is_room():
    lay = radial.radial(grupos.agrupar(["png"]))
    x, y = radial.posicionar(lay, 960, 540, 1920, 1080)
    assert (x + lay.ancora_x, y + lay.ancora_y) == (960, 540)


# ---------- desenho ----------

def _painel(forma="radial", escuro=False, **kw):
    lay = radial.montar(grupos.agrupar(["png", "jpg", "txt", "docx"]), forma)
    pal = tema.paleta(tema.Aparencia(**kw), escuro=escuro)
    return lay, pal


@pytest.mark.parametrize("forma", ["radial", "cartao"])
def test_corners_are_transparent_and_body_is_opaque(forma):
    lay, pal = _painel(forma)
    img = render.desenhar(lay, pal, "contrato.pdf", "pdf")
    assert img.mode == "RGBA" and img.size == (lay.largura, lay.altura)
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((lay.largura - 1, lay.altura - 1))[3] == 0
    it = lay.itens[0]
    assert img.getpixel((round(it.x), round(it.y - it.h / 2 + 3)))[3] > 240


def test_hover_paints_box_with_group_color():
    lay, pal = _painel(cores_grupo={"Imagem": "#FF0000"})
    it = next(i for i in lay.itens if i.fmt == "png")
    normal = render.desenhar(lay, pal, "a.pdf", "pdf")
    hover = render.desenhar(lay, pal, "a.pdf", "pdf", hover="png")
    ponto = (round(it.x - it.w / 2 + 6), round(it.y))  # dentro da caixa, fora do texto
    assert hover.getpixel(ponto)[:3] == (255, 0, 0)
    assert normal.getpixel(ponto)[:3] != (255, 0, 0)


def test_opacity_setting_changes_background_alpha():
    lay, _ = _painel()
    pal = tema.paleta(tema.PADRAO, escuro=False)
    ponto = (round(lay.ancora_x), round(lay.ancora_y - lay.fundo_r + 8))  # anel externo, sem caixas
    a1 = render.desenhar(lay, pal, "a", "pdf", opacidade=1.0).getpixel(ponto)[3]
    a2 = render.desenhar(lay, pal, "a", "pdf", opacidade=0.7).getpixel(ponto)[3]
    assert a1 > 245 and a2 < 200


def test_cached_frames_match_full_render():
    lay, pal = _painel()
    pintor = render.Pintor(lay, pal, "a.pdf", "pdf")
    a = pintor.quadro(hover="txt")
    b = render.desenhar(lay, pal, "a.pdf", "pdf", hover="txt")
    assert a.tobytes() == b.tobytes()


def test_gallery(tmp_path):
    arquivos = render.salvar_galeria(tmp_path)
    assert len(arquivos) == len(tema.PRESETS) * 2 * 2 * 2
    with Image.open(arquivos[0]) as im:
        assert im.size[0] > 200
