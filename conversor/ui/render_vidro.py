"""Desenho do estilo "Vidro": pílulas de vidro ao redor do arquivo (glassmorphism).

Cada pílula, de baixo para cima: sombra suave → corpo (o fundo de verdade
desfocado, quando o Windows deixou capturar; senão a cor translúcida) → véu
branco (vidro fosco) → tinta da cor escolhida → brilho no alto → borda clara
em cima e mais escura embaixo → texto. Desenhado em 3× e reduzido (sem
serrilhado), como o resto do painel. Fora das pílulas tudo é transparente:
o clique passa (regra 19).
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

from conversor.ui import grupos as grp
from conversor.ui import vidro
from conversor.ui.radial import MAIS, Layout
from conversor.ui.render import SS, _desfocar, _encurtar, _icone_arquivo, _misturar, _rgba, fonte
from conversor.ui.tema import Paleta

ERRO = "#FF3B30"


def preparar_fundo(fundo_atras: Image.Image | None, intensidade: float) -> Image.Image | None:
    """O que está atrás do painel (captura de tela), já desfocado (1×, RGB)."""
    if fundo_atras is None:
        return None
    raio = vidro.parametros(intensidade)["desfoque"]
    return fundo_atras.convert("RGB").filter(ImageFilter.GaussianBlur(raio))


def _media(img: Image.Image) -> tuple:
    return img.resize((1, 1), Image.BOX).getpixel((0, 0))[:3]


def _corte(alfa: Image.Image) -> Image.Image:
    # Restos quase invisíveis da sombra viram transparência total (regra 19).
    return alfa.point(lambda v: 0 if v < 8 else v)


def pilula(w: float, h: float, raio: float, s: float, cor: str, intensidade: float,
           recorte: Image.Image | None, texto: str, fnt, destaque: bool = False,
           ponto: str | None = None, sombra: bool = True) -> Image.Image:
    """Uma pílula de vidro pronta (1×), com folga em volta para sombra e brilho.
    `recorte`: o fundo desfocado exatamente atrás dela (w×h, 1×) ou None."""
    par = vidro.parametros(intensidade)
    folga = round(10 * s / SS)  # s = SS × escala: px de 1× = s / SS
    W, H = round(w + 2 * folga) * SS, round(h + 2 * folga) * SS
    x0, y0 = folga * SS, folga * SS
    x1, y1 = x0 + w * SS, y0 + h * SS
    r = raio * SS
    caixa = (x0, y0, x1, y1)
    mascara = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(caixa, radius=r, fill=255)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if sombra:
        sombra_l = Image.new("L", (W, H), 0)
        sombra_l.paste(mascara.point(lambda v: v * 0.30), (0, round(3 * s)))
        sombra_img = Image.new("RGBA", (W, H), (10, 25, 60, 0))
        sombra_img.putalpha(sombra_l.filter(ImageFilter.GaussianBlur(5 * SS)))
        img = Image.alpha_composite(img, sombra_img)

    fundos = [_media(recorte)] if recorte is not None else vidro.FUNDOS_DESCONHECIDOS
    alfa, cor_texto = vidro.tinta_legivel(fundos, cor, par["alfa_tinta"], par["nevoa"])
    tinta = _misturar(cor, "#FFFFFF", 0.14) if destaque else cor
    corpo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if recorte is not None:
        # Vidro de verdade: o fundo desfocado + véu + tinta, opaco.
        base = recorte.convert("RGB").resize((round(w * SS), round(h * SS)), Image.BILINEAR)
        base = Image.blend(base, Image.new("RGB", base.size, (255, 255, 255)), par["nevoa"])
        base = Image.blend(base, Image.new("RGB", base.size, _rgba(tinta)[:3]), alfa)
        corpo.paste(base.convert("RGBA"), (x0, y0))
        corpo.putalpha(mascara)
    else:
        # Sem fundo: cor translúcida (o que estiver atrás aparece por ela).
        corpo = Image.new("RGBA", (W, H), _rgba(_misturar(tinta, "#FFFFFF", par["nevoa"]), alfa))
        corpo.putalpha(mascara.point(lambda v: round(v * alfa)))
    img = Image.alpha_composite(img, corpo)

    # Brilho no alto (reflexo do vidro): gradiente branco até ~55% da altura.
    brilho = Image.new("L", (W, H), 0)
    db = ImageDraw.Draw(brilho)
    altura = (y1 - y0) * 0.55
    for k in range(int(altura)):
        db.line((x0, y0 + k, x1, y0 + k), fill=round(110 * (1 - k / altura) ** 1.6))
    brilho = Image.composite(brilho, Image.new("L", (W, H), 0), mascara)
    camada = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    camada.putalpha(brilho)
    img = Image.alpha_composite(img, camada)

    # Borda: clara em volta, mais escura na metade de baixo (volume).
    d = ImageDraw.Draw(img)
    esp = max(1, round(1.2 * SS))
    d.rounded_rectangle(caixa, radius=r, outline=(255, 255, 255, 150), width=esp)
    meio = Image.new("L", (W, H), 0)
    ImageDraw.Draw(meio).rectangle((0, (y0 + y1) / 2, W, H), fill=70)
    escura = Image.new("RGBA", (W, H), (*_rgba(_misturar(cor, "#000000", 0.45))[:3], 0))
    contorno = Image.new("L", (W, H), 0)
    ImageDraw.Draw(contorno).rounded_rectangle(caixa, radius=r, outline=255, width=esp)
    escura.putalpha(Image.composite(meio, Image.new("L", (W, H), 0), contorno))
    img = Image.alpha_composite(img, escura)

    if destaque:  # halo claro em volta, como o botão "aceso"
        halo = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        halo.putalpha(_desfocar(contorno, 4 * SS).point(lambda v: min(255, v * 2)))
        img = Image.alpha_composite(halo, img)

    d = ImageDraw.Draw(img)
    cx = (x0 + x1) / 2
    if ponto:
        pr = 3 * s
        px = x0 + 12 * s
        d.ellipse((px - pr, (y0 + y1) / 2 - pr, px + pr, (y0 + y1) / 2 + pr), fill=_rgba(ponto))
        cx += 4 * s
    texto = _encurtar(texto, fnt, (x1 - x0) * 0.84)
    sombra_txt = (0, 0, 0, 70) if cor_texto == vidro.TEXTO_CLARO else (255, 255, 255, 90)
    d.text((cx, (y0 + y1) / 2 + SS), texto, font=fnt, fill=sombra_txt, anchor="mm")
    d.text((cx, (y0 + y1) / 2), texto, font=fnt, fill=_rgba(cor_texto), anchor="mm")

    img = img.resize((W // SS, H // SS), Image.LANCZOS)
    r_, g_, b_, a_ = img.split()
    return Image.merge("RGBA", (r_, g_, b_, _corte(a_)))


def _recorte(fundo: Image.Image | None, x: float, y: float, w: float, h: float) -> Image.Image | None:
    if fundo is None:
        return None
    return fundo.crop((round(x - w / 2), round(y - h / 2), round(x + w / 2), round(y + h / 2)))


def desenhar_base(lay: Layout, pal: Paleta, nome: str, fmt_origem: str, estilo: dict,
                  fundo: Image.Image | None, centro_ativo: bool = False) -> Image.Image:
    """Disco de vidro com o ícone do arquivo e, embaixo, o nome numa cápsula."""
    s = SS * lay.escala
    img = Image.new("RGBA", (lay.largura, lay.altura), (0, 0, 0, 0))
    cx, cy, cr = lay.ancora_x, lay.ancora_y, lay.centro_r
    cor = estilo["cor"]
    disco = pilula(2 * cr, 2 * cr, cr, s, cor, estilo["intensidade"],
                   _recorte(fundo, cx, cy, 2 * cr, 2 * cr), "", fonte(round(13 * s)), centro_ativo)
    img.alpha_composite(disco, (round(cx - disco.width / 2), round(cy - disco.height / 2)))
    icone = Image.new("RGBA", (round(2 * cr * SS), round(2 * cr * SS)), (0, 0, 0, 0))
    _icone_arquivo(ImageDraw.Draw(icone), cr * SS, cr * SS, 15 * s, pal, fmt_origem)
    icone = icone.resize((round(2 * cr), round(2 * cr)), Image.LANCZOS)
    img.alpha_composite(icone, (round(cx - cr), round(cy - cr)))
    f_nome = fonte(round(10.5 * s), negrito=False)
    nome_curto = _encurtar(nome, f_nome, 150 * s)
    larg = f_nome.getlength(nome_curto) / SS + 20 * lay.escala
    alt = 20 * lay.escala
    ny = cy + cr + 4 * lay.escala + alt / 2
    capsula = pilula(larg, alt, alt / 2, s, cor, estilo["intensidade"],
                     _recorte(fundo, cx, ny, larg, alt), nome_curto, f_nome, sombra=False)
    img.alpha_composite(capsula, (round(cx - capsula.width / 2), round(ny - capsula.height / 2)))
    return img


def desenhar_item(it, lay: Layout, pal: Paleta, estilo: dict, fundo: Image.Image | None,
                  ativo: bool = False, estado: str | None = None) -> tuple[Image.Image, tuple[int, int]]:
    s = SS * lay.escala
    rotulo = "Mais…" if it.fmt == MAIS else grp.rotulo(it.fmt)
    rotulo = {"ok": "✓ " + rotulo, "ocupado": "…", "erro": "✕ " + rotulo}.get(estado, rotulo)
    cor = ERRO if estado == "erro" else estilo["cor"]
    w, h = (it.w * 1.06, it.h * 1.06) if ativo else (it.w, it.h)
    ponto = None if it.fmt == MAIS else pal.grupos.get(it.grupo)
    tile = pilula(w, h, h / 2, s, cor, estilo["intensidade"], _recorte(fundo, it.x, it.y, w, h),
                  rotulo, fonte(round(13 * s)), ativo or estado in ("ok", "ocupado"), ponto)
    return tile, (round(it.x - tile.width / 2), round(it.y - tile.height / 2))


def papel_de_parede(largura: int, altura: int, tipo: str = "foto") -> Image.Image:
    """Fundos de exemplo (prévia da Aparência e galeria): "claro", "escuro" ou
    "foto" (colorido e cheio de formas, o caso mais difícil para ler texto)."""
    img = Image.new("RGB", (largura, altura))
    d = ImageDraw.Draw(img)
    cores = {"claro": ((246, 247, 251), (206, 216, 236)), "escuro": ((18, 22, 38), (44, 52, 86)),
             "foto": ((255, 170, 90), (60, 120, 220))}[tipo]
    for y in range(altura):
        t = y / max(1, altura - 1)
        d.line((0, y, largura, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(*cores)))
    if tipo == "foto":
        d.ellipse((largura * 0.55, altura * 0.05, largura * 0.95, altura * 0.45), fill=(255, 236, 160))
        d.polygon([(0, altura), (largura * 0.25, altura * 0.5), (largura * 0.5, altura * 0.75),
                   (largura * 0.78, altura * 0.42), (largura, altura * 0.7), (largura, altura)], fill=(34, 70, 60))
        d.rectangle((largura * 0.05, altura * 0.08, largura * 0.3, altura * 0.3), fill=(240, 80, 120))
    return img


def salvar_galeria(pasta, origem: str = "png", arquivo: str = "foto_ferias.png") -> list:
    """Prévias do Vidro: cada cor × fundo (claro, escuro, foto) e o simulado (Mac)."""
    from conversor.core import registry
    from conversor.ui import radial, tema
    from conversor.ui.render import Pintor

    pasta.mkdir(parents=True, exist_ok=True)
    lay = radial.montar(grp.agrupar(registry.targets_for(origem, only_available=False)), "vidro")
    pal = tema.paleta(tema.Aparencia(), escuro=False)
    saidas = []
    for nome_cor, cor in vidro.CORES.items():
        estilo = {"cor": cor, "intensidade": vidro.INTENSIDADE_PADRAO}
        for tipo in ("claro", "escuro", "foto", "simulado"):
            papel = papel_de_parede(lay.largura, lay.altura, "foto" if tipo == "simulado" else tipo)
            captura = None if tipo == "simulado" else papel
            img = Pintor(lay, pal, arquivo, origem, estilo=estilo, fundo_atras=captura).quadro(hover=lay.itens[0].fmt)
            caminho = pasta / f"vidro-{nome_cor}-{tipo}.png"
            Image.alpha_composite(papel.convert("RGBA"), img).convert("RGB").save(caminho)
            saidas.append(caminho)
    return saidas
