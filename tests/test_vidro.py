"""Estilo Vidro: órbita, contraste do texto sobre o fundo real, transparência
fora das pílulas, uso do fundo capturado, animação e configuração."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from conversor.ui import grupos, radial, render, render_vidro, tema, vidro
from conversor.ui.tema import contraste


def _lay(destinos=("png", "jpg", "pdf", "txt", "stl")):
    return radial.montar(grupos.agrupar(list(destinos)), "vidro")


def _pal():
    return tema.paleta(tema.Aparencia(), escuro=False)


# ---------- contraste ----------

@pytest.mark.parametrize("cor", list(vidro.CORES))
@pytest.mark.parametrize("fundo", [(255, 255, 255), (0, 0, 0), (250, 220, 120), (40, 120, 220)])
def test_text_contrast_on_real_backdrop(cor, fundo):
    par = vidro.parametros(vidro.INTENSIDADE_PADRAO)
    alfa, texto = vidro.tinta_legivel([fundo], vidro.CORES[cor], par["alfa_tinta"], par["nevoa"])
    efetiva = vidro.misturar(fundo, vidro.CORES[cor], alfa, par["nevoa"])
    assert contraste(texto, efetiva) >= vidro.MINIMO[texto]


def test_colored_glass_keeps_white_text_like_the_reference():
    par = vidro.parametros(0.6)
    _, texto = vidro.tinta_legivel([(70, 150, 230)], vidro.CORES["Azul"], par["alfa_tinta"], par["nevoa"])
    assert texto == vidro.TEXTO_CLARO
    _, texto = vidro.tinta_legivel([(70, 150, 230)], vidro.CORES["Neutro"], par["alfa_tinta"], par["nevoa"])
    assert texto == vidro.TEXTO_ESCURO


def test_unknown_backdrop_is_legible_over_white_and_black():
    par = vidro.parametros(0.6)
    for cor in vidro.CORES.values():
        alfa, texto = vidro.tinta_legivel(vidro.FUNDOS_DESCONHECIDOS, cor, par["alfa_tinta"], par["nevoa"])
        for f in vidro.FUNDOS_DESCONHECIDOS:
            assert contraste(texto, vidro.misturar(f, cor, alfa, par["nevoa"])) >= vidro.MINIMO[texto]


# ---------- desenho ----------

def test_only_pills_capture_clicks():
    lay = _lay()
    img = render.Pintor(lay, _pal(), "a.png", "png").quadro()
    assert img.getpixel((0, 0))[3] == 0, "canto transparente: o clique passa"
    for it in lay.itens:
        assert img.getpixel((round(it.x), round(it.y - it.h / 2 + 4)))[3] > 100, it.fmt
    a, b = lay.itens[0], lay.itens[1]  # entre duas pílulas vizinhas: vazio
    meio = (round((a.x + b.x) / 2), round((a.y + b.y) / 2))
    if not any(i.contem(*meio) for i in lay.itens):
        assert img.getpixel(meio)[3] < 60


def test_real_glass_uses_the_captured_backdrop():
    lay = _lay()
    estilo = {"cor": vidro.CORES["Azul"], "intensidade": 0.6}
    vermelho = Image.new("RGB", (lay.largura, lay.altura), (220, 30, 30))
    verde = Image.new("RGB", (lay.largura, lay.altura), (30, 180, 60))
    it = lay.itens[0]
    ponto = (round(it.x - it.w / 2 + 6), round(it.y + it.h * 0.3))  # dentro, fora do texto
    a = render.Pintor(lay, _pal(), "a.png", "png", estilo=estilo, fundo_atras=vermelho).quadro().getpixel(ponto)
    b = render.Pintor(lay, _pal(), "a.png", "png", estilo=estilo, fundo_atras=verde).quadro().getpixel(ponto)
    assert a[3] == 255 and b[3] == 255, "vidro de verdade é opaco (o fundo já está nele)"
    assert a[0] > b[0] and b[1] > a[1], "a cor de trás aparece através do vidro"


def test_simulated_glass_is_translucent():
    lay = _lay()
    it = lay.itens[0]
    ponto = (round(it.x - it.w / 2 + 6), round(it.y + it.h * 0.3))
    alfa = render.Pintor(lay, _pal(), "a.png", "png").quadro().getpixel(ponto)[3]
    assert 120 < alfa < 255


def test_hover_makes_the_pill_bigger_and_brighter():
    lay = _lay()
    p = render.Pintor(lay, _pal(), "a.png", "png")
    it = lay.itens[0]
    normal = p._item(it, False, None)[0]
    aceso = p._item(it, True, None)[0]
    assert aceso.width > normal.width


def test_entrance_animation_starts_at_the_file_and_ends_in_orbit():
    lay = _lay()
    p = render.Pintor(lay, _pal(), "a.png", "png")
    it = lay.itens[0]
    longe = (round(it.x), round(it.y))
    assert p.quadro(progresso=0.0).getpixel(longe)[3] == 0, "no início a pílula ainda está no centro"
    assert p.quadro(progresso=1.0).getpixel(longe)[3] > 100


@pytest.mark.parametrize("tipo", ["claro", "escuro", "foto"])
def test_wallpapers_for_preview(tipo):
    assert render_vidro.papel_de_parede(120, 80, tipo).size == (120, 80)


# ---------- captura com zoom (Windows) ----------

def test_capture_crop_respects_display_scaling():
    from conversor.atalho.painel import recortar_escalado

    tela = Image.new("RGB", (2880, 1620), "white")  # 1920×1080 com zoom de 150%
    tela.paste((255, 0, 0), (1500, 600, 1800, 900))  # (1000, 400) lógico, 200×200
    r = recortar_escalado(tela, 1000, 400, 200, 200, 1920)
    assert r.size == (200, 200) and r.getpixel((5, 5)) == (255, 0, 0) and r.getpixel((195, 195)) == (255, 0, 0)
    assert recortar_escalado(tela, 1900, 400, 200, 200, 1920) is None, "fora da tela: vidro simulado"


# ---------- configuração ----------

def test_glass_is_default_and_old_files_migrate_once(tmp_path):
    assert tema.PADRAO.forma == "vidro" and tema.PADRAO.animacao is True
    arq = tmp_path / "aparencia.json"
    arq.write_text(json.dumps({"tema": "Rosa", "forma": "radial"}), encoding="utf-8")
    a = tema.carregar(arq)
    assert a.forma == "vidro" and a.tema == "Rosa", "atualização: passa ao Vidro, mantém o resto"
    tema.salvar(tema.replace(a, forma="cartao"), arq)
    assert tema.carregar(arq).forma == "cartao", "depois a escolha da pessoa vale"


@pytest.mark.parametrize("campo,valor", [("vidro_cor", "Laranja"), ("vidro_cor", "#12345"),
                                         ("vidro_intensidade", 1.5)])
def test_invalid_glass_settings_are_rejected(campo, valor):
    assert tema.validar(tema.replace(tema.PADRAO, **{campo: valor}))


def test_custom_hex_glass_color():
    a = tema.replace(tema.PADRAO, vidro_cor="#FF8800", vidro_intensidade=0.2)
    assert not tema.validar(a) and tema.estilo_vidro(a) == {"cor": "#FF8800", "intensidade": 0.2}
