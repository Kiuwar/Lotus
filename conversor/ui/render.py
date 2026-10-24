"""Desenha o painel flutuante como imagem RGBA (Pillow).

Desenha em 3× e reduz com filtro LANCZOS: curvas e cantos ficam lisos, sem
serrilhado, também no Windows 10. A mesma função gera o painel de verdade, a
pré-visualização da janela "Aparência" e as imagens da galeria do CI.
"""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from conversor.ui import grupos as grp
from conversor.ui.radial import CENTRO, MAIS, Layout
from conversor.ui.tema import Paleta, legivel, texto_sobre

SS = 3  # supersampling

_FONTES = {
    "win32": ["segoeuib.ttf", "segoeui.ttf"],
    "darwin": ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc"],
}
_FALLBACK = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


@lru_cache(maxsize=32)
def fonte(tamanho: int, negrito: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatos = list(_FONTES.get(sys.platform, []))
    if sys.platform == "win32" and not negrito:
        candidatos.reverse()
    candidatos += _FALLBACK if negrito else _FALLBACK[::-1]
    for c in candidatos:
        try:
            return ImageFont.truetype(c, tamanho)
        except OSError:
            continue
    return ImageFont.load_default(tamanho)


def _rgba(h: str, alfa: float = 1.0) -> tuple[int, int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), round(255 * alfa)


def _misturar(a: str, b: str, t: float) -> str:
    ca, cb = _rgba(a), _rgba(b)
    return "#" + "".join(f"{round(ca[i] + (cb[i] - ca[i]) * t):02X}" for i in range(3))


def _encurtar(texto: str, f, largura: float) -> str:
    if f.getlength(texto) <= largura:
        return texto
    while texto and f.getlength(texto + "…") > largura:
        texto = texto[:-1]
    return texto + "…"


def _texto_centro(d: ImageDraw.ImageDraw, x: float, y: float, s: str, f, cor) -> None:
    d.text((x, y), s, font=f, fill=cor, anchor="mm")


def _sombra(img: Image.Image, forma: Image.Image, raio: int, alfa: float, dy: int) -> Image.Image:
    """Sombra suave como a do macOS: a máscara da forma, deslocada e desfocada."""
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    preto = Image.new("RGBA", img.size, (0, 0, 0, round(255 * alfa)))
    sombra.paste(preto, (0, dy), forma)
    sombra = sombra.filter(ImageFilter.GaussianBlur(raio))
    return Image.alpha_composite(sombra, img)


def desenhar_base(lay: Layout, pal: Paleta, nome: str, fmt_origem: str, opacidade: float = 0.96,
                  centro_ativo: bool = False) -> Image.Image:
    """Tudo menos as caixas de formato (desenhado uma vez por painel)."""
    hover = CENTRO if centro_ativo else None
    s = SS * lay.escala
    W, H = lay.largura * SS, lay.altura * SS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mascara = Image.new("L", (W, H), 0)
    dm = ImageDraw.Draw(mascara)
    margem = lay.margem * SS

    # ---- fundo ----
    if lay.forma == "radial":
        cx, cy, r = lay.ancora_x * SS, lay.ancora_y * SS, lay.fundo_r * SS
        dm.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    else:
        dm.rounded_rectangle((margem, margem, W - margem, H - margem), radius=18 * s, fill=255)
    fundo = Image.new("RGBA", (W, H), _rgba(pal.fundo, opacidade))
    img.paste(fundo, (0, 0), mascara)
    img = _sombra(img, mascara, round(14 * s), 0.28 if pal.escuro else 0.18, round(6 * s))
    d = ImageDraw.Draw(img)
    contorno = _rgba("#FFFFFF" if pal.escuro else "#000000", 0.10)
    if lay.forma == "radial":
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=contorno, width=max(1, round(s)))
    else:
        d.rounded_rectangle((margem, margem, W - margem, H - margem), radius=18 * s,
                            outline=contorno, width=max(1, round(s)))

    f_item = fonte(round(13 * s))
    f_rot = fonte(round(10 * s))
    f_nome = fonte(round(10.5 * s), negrito=False)

    # ---- faixas e rótulos dos grupos (radial) ----
    if lay.forma == "radial":
        for fx in lay.faixas:
            cor = pal.grupos.get(fx.grupo, pal.destaque)
            camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dc = ImageDraw.Draw(camada)
            rm, larg = (fx.r_ext + fx.r_int) / 2 * SS, (fx.r_ext - fx.r_int) * SS
            tinta = _rgba(cor, 0.17 if pal.escuro else 0.14)
            dc.arc((cx - rm - larg / 2, cy - rm - larg / 2, cx + rm + larg / 2, cy + rm + larg / 2),
                   fx.ang_ini, fx.ang_fim, fill=tinta, width=round(larg))
            for a in (fx.ang_ini, fx.ang_fim):  # pontas arredondadas, estilo macOS
                px, py = cx + rm * math.cos(math.radians(a)), cy + rm * math.sin(math.radians(a))
                dc.ellipse((px - larg / 2, py - larg / 2, px + larg / 2, py + larg / 2), fill=tinta)
            img = Image.alpha_composite(img, camada)
            _rotulo_curvo(img, fx.rotulo_x * SS, fx.rotulo_y * SS, fx.rotulo_ang, fx.grupo.upper(), f_rot,
                          _rgba(legivel(cor, pal.fundo)))
        d = ImageDraw.Draw(img)

        # círculo central: o arquivo
        cr = lay.centro_r * SS
        centro_cor = pal.destaque if hover == CENTRO else pal.superficie
        d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=_rgba(centro_cor),
                  outline=_rgba(pal.destaque, 0.55), width=max(1, round(1.5 * s)))
        _icone_arquivo(d, cx, cy - 9 * s, 13 * s, pal, fmt_origem)
        txt = texto_sobre(centro_cor) if hover == CENTRO else pal.texto_sec
        _texto_centro(d, cx, cy + 20 * s, _encurtar(nome, f_nome, cr * 1.6), f_nome, _rgba(txt))
    else:
        # cabeçalho do cartão: ícone + nome + "Converter para"
        _icone_arquivo(d, margem + 26 * s, margem + 30 * s, 11 * s, pal, fmt_origem)
        d.text((margem + 46 * s, margem + 23 * s), _encurtar(nome, f_item, W - margem * 2 - 60 * s),
               font=f_item, fill=_rgba(pal.texto), anchor="lm")
        d.text((margem + 46 * s, margem + 40 * s), "Converter para", font=f_nome,
               fill=_rgba(pal.texto_sec), anchor="lm")
        for g, y in lay.secoes:
            d.text((margem + 16 * s, y * SS + 8 * s), g.upper(), font=f_rot,
                   fill=_rgba(legivel(pal.grupos.get(g, pal.destaque), pal.fundo)), anchor="lm")

    img = img.resize((lay.largura, lay.altura), Image.LANCZOS)
    # Restos quase invisíveis da sombra viram transparência total: no Windows,
    # pixel com alfa > 0 numa janela em camadas ainda captura cliques.
    r, g, b, a = img.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: 0 if v < 8 else v)))


def desenhar_item(it, lay: Layout, pal: Paleta, ativo: bool = False,
                  estado: str | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """Uma caixa de formato, já reduzida, e onde colá-la na base."""
    s = SS * lay.escala
    folga = 2  # pixels em volta, para o antisserrilhado da borda
    w, h = round(it.w + 2 * folga), round(it.h + 2 * folga)
    ox, oy = round(it.x - w / 2), round(it.y - h / 2)
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cor = pal.destaque if it.fmt == MAIS else pal.grupos.get(it.grupo, pal.destaque)
    ativo = ativo or estado in ("ocupado", "ok")
    if estado == "erro":
        preench, borda = "#FF3B30", "#FF3B30"
    elif ativo:
        preench, borda = cor, cor
    else:
        preench, borda = _misturar(pal.superficie, cor, 0.10), _misturar(pal.superficie, cor, 0.55)
    # posição exata da caixa dentro do recorte (respeita a fração de pixel)
    x0, y0 = (it.x - it.w / 2 - ox) * SS, (it.y - it.h / 2 - oy) * SS
    x1, y1 = x0 + it.w * SS, y0 + it.h * SS
    d.rounded_rectangle((x0, y0, x1, y1), radius=it.raio * SS, fill=_rgba(preench),
                        outline=_rgba(borda), width=max(1, round(1.5 * s)))
    rotulo = "Mais…" if it.fmt == MAIS else grp.rotulo(it.fmt)
    rotulo = {"ok": "✓ " + rotulo, "ocupado": "…", "erro": "✕ " + rotulo}.get(estado, rotulo)
    f = fonte(round(13 * s))
    cor_txt = texto_sobre(preench) if (ativo or estado == "erro") else pal.texto
    _texto_centro(d, (x0 + x1) / 2, (y0 + y1) / 2, _encurtar(rotulo, f, (x1 - x0) * 0.9), f, _rgba(cor_txt))
    return img.resize((w, h), Image.LANCZOS), (ox, oy)


class Pintor:
    """Monta quadros do painel rapidamente: a base é desenhada uma vez e cada
    caixa (normal / destacada / estados) só na primeira vez que aparece."""

    def __init__(self, lay: Layout, pal: Paleta, nome: str, fmt_origem: str, opacidade: float = 0.96):
        self.lay, self.pal = lay, pal
        self._bases = {
            False: desenhar_base(lay, pal, nome, fmt_origem, opacidade),
        }
        self._args = (nome, fmt_origem, opacidade)
        self._itens: dict = {}

    def _base(self, centro_ativo: bool) -> Image.Image:
        if centro_ativo not in self._bases:
            self._bases[centro_ativo] = desenhar_base(self.lay, self.pal, *self._args, centro_ativo=True)
        return self._bases[centro_ativo]

    def quadro(self, hover: str | None = None, estados: dict | None = None) -> Image.Image:
        estados = estados or {}
        img = self._base(hover == CENTRO).copy()
        for it in self.lay.itens:
            chave = (it.fmt, hover == it.fmt, estados.get(it.fmt))
            if chave not in self._itens:
                self._itens[chave] = desenhar_item(it, self.lay, self.pal, chave[1], chave[2])
            tile, pos = self._itens[chave]
            img.alpha_composite(tile, pos)
        return img


def desenhar(lay: Layout, pal: Paleta, nome: str, fmt_origem: str, opacidade: float = 0.96,
             hover: str | None = None, estados: dict | None = None) -> Image.Image:
    """Painel completo num só passo (prévias e testes). estados: {fmt: "ocupado"|"ok"|"erro"}."""
    return Pintor(lay, pal, nome, fmt_origem, opacidade).quadro(hover, estados)


def _rotulo_curvo(img: Image.Image, x: float, y: float, ang: float, texto: str, f, cor) -> None:
    """Texto tangente ao anel, nunca de cabeça para baixo."""
    l, t, r, b = f.getbbox(texto)
    pad = 4
    camada = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(camada).text((pad - l, pad - t), texto, font=f, fill=cor)
    giro = -(ang + 90)              # tangente ao círculo
    if 0 < (ang % 360) < 180:       # metade de baixo: vira para ler da esquerda p/ direita
        giro += 180
    camada = camada.rotate(giro, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(camada, (round(x - camada.width / 2), round(y - camada.height / 2)))


def _icone_arquivo(d: ImageDraw.ImageDraw, x: float, y: float, t: float, pal: Paleta, fmt: str) -> None:
    """Folha com canto dobrado e a extensão embaixo (ícone genérico de arquivo)."""
    w, h, dobra = t * 1.5, t * 1.9, t * 0.5
    x0, y0, x1, y1 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
    cor = pal.grupos.get(grp.FAMILIA.get(fmt, "Documento"), pal.destaque)
    d.polygon([(x0, y0), (x1 - dobra, y0), (x1, y0 + dobra), (x1, y1), (x0, y1)],
              fill=_rgba(cor), outline=_rgba(cor))
    d.polygon([(x1 - dobra, y0), (x1 - dobra, y0 + dobra), (x1, y0 + dobra)],
              fill=_rgba(_misturar(cor, "#FFFFFF", 0.45)))
    f = fonte(max(6, round(t * 0.55)))
    _texto_centro(d, x, y + h * 0.18, grp.rotulo(fmt)[:4], f, _rgba(texto_sobre(cor)))


def salvar_galeria(pasta: Path) -> list[Path]:
    """Gera as imagens de prévia do design (usado pelo CI e pela documentação)."""
    from conversor.core import registry
    from conversor.ui import radial, tema

    pasta.mkdir(parents=True, exist_ok=True)
    saidas = []
    for nome_tema in tema.PRESETS:
        for escuro in (False, True):
            pal = tema.paleta(tema.Aparencia(tema=nome_tema), escuro=escuro)
            for origem, arquivo in (("pdf", "Contrato de locação.pdf"), ("png", "foto_ferias.png")):
                g = grp.agrupar(registry.targets_for(origem, only_available=False))
                for forma in ("radial", "cartao"):
                    lay = radial.montar(g, forma)
                    hover = lay.itens[0].fmt
                    img = desenhar(lay, pal, arquivo, origem, hover=hover)
                    fundo = Image.new("RGBA", img.size, (40, 44, 52, 255) if escuro else (210, 214, 220, 255))
                    p = pasta / f"{forma}-{nome_tema.replace(' ', '')}-{'escuro' if escuro else 'claro'}-{origem}.png"
                    Image.alpha_composite(fundo, img).convert("RGB").save(p)
                    saidas.append(p)
    return saidas
