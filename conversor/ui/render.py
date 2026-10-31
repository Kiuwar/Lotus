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


# ---------- efeito holográfico ----------

# Cores do brilho iridescente (como a película de um holograma), em volta.
IRIDESCENTE_ESCURO = ["#00E5FF", "#7C5CFF", "#FF4FD8", "#FFB46B", "#5CFFC1", "#00E5FF"]
IRIDESCENTE_CLARO = ["#5BD8FF", "#A28BFF", "#FF8AD8", "#FFC98B", "#7FE8C8", "#5BD8FF"]


def _cor_em(paradas: list[str], t: float) -> str:
    t = t % 1.0
    pos = t * (len(paradas) - 1)
    i = min(int(pos), len(paradas) - 2)
    return _misturar(paradas[i], paradas[i + 1], pos - i)


def _iridescente(escuro: bool) -> list[str]:
    return IRIDESCENTE_ESCURO if escuro else IRIDESCENTE_CLARO


def _gradiente_horizontal(w: int, h: int, paradas: list[str], alfa: float = 1.0) -> Image.Image:
    faixa = Image.new("RGBA", (256, 1))
    faixa.putdata([_rgba(_cor_em(paradas, i / 255 * 0.999), alfa) for i in range(256)])
    return faixa.resize((max(1, w), max(1, h)), Image.BILINEAR)


def _desfocar(camada: Image.Image, raio: float) -> Image.Image:
    """Desfoque gaussiano numa cópia reduzida (o halo é borrado de qualquer
    jeito; em 3× o desfoque direto deixava o painel lento para abrir)."""
    w, h = camada.size
    pequena = camada.resize((max(1, w // SS), max(1, h // SS)), Image.BILINEAR)
    return pequena.filter(ImageFilter.GaussianBlur(raio / SS)).resize((w, h), Image.BILINEAR)


def _com_halo(camada: Image.Image, raio: float, forca: float = 1.0) -> Image.Image:
    """Halo neon: a camada desfocada por baixo da própria camada (uma camada só)."""
    halo = _desfocar(camada, raio)
    if forca != 1.0:
        halo.putalpha(halo.getchannel("A").point(lambda v: min(255, round(v * forca))))
    return Image.alpha_composite(halo, camada)


def _brilho(img: Image.Image, camada: Image.Image, raio: float, forca: float = 1.0) -> Image.Image:
    return Image.alpha_composite(img, _com_halo(camada, raio, forca))


def _anel_holo(img: Image.Image, cx: float, cy: float, r: float, s: float, pal: Paleta) -> Image.Image:
    return Image.alpha_composite(img, _camada_anel(img.size, cx, cy, r, s, pal.escuro, pal.texto))


# O anel não depende do arquivo clicado: fica em cache e só a 1ª abertura do
# painel paga o desenho (~0,2 s); as seguintes só colam a camada pronta.
@lru_cache(maxsize=8)
def _camada_anel(tamanho: tuple, cx: float, cy: float, r: float, s: float, escuro: bool,
                 texto: str) -> Image.Image:
    """Borda iridescente com brilho e marcas finas de mostrador (estilo HUD)."""
    W, H = tamanho
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    larg = max(2, round(2.2 * s))
    paradas = _iridescente(escuro)
    passos = 180
    for k in range(passos):  # arco em 180 fatias: gradiente cônico sem numpy
        a0, a1 = k * 360 / passos - 90, (k + 1.4) * 360 / passos - 90
        d.arc((cx - r, cy - r, cx + r, cy + r), a0, a1, fill=_rgba(_cor_em(paradas, k / passos)),
              width=larg)
    img = _com_halo(camada, 5 * s, 0.9 if escuro else 0.5)
    d = ImageDraw.Draw(img)
    marca = _rgba(texto, 0.22 if escuro else 0.16)
    ri = r - 6 * s
    for k in range(72):
        ang = math.radians(k * 5)
        comp = (5 if k % 6 == 0 else 2.5) * s
        x0, y0 = cx + ri * math.cos(ang), cy + ri * math.sin(ang)
        x1, y1 = cx + (ri - comp) * math.cos(ang), cy + (ri - comp) * math.sin(ang)
        d.line((x0, y0, x1, y1), fill=marca, width=max(1, round(0.8 * s)))
    for frac in (0.62, 0.86):  # círculos de grade, quase invisíveis
        rr_ = r * frac
        d.ellipse((cx - rr_, cy - rr_, cx + rr_, cy + rr_), outline=_rgba(texto, 0.05),
                  width=max(1, round(s)))
    return img


def _moldura_holo(img: Image.Image, caixa: tuple, raio: float, s: float, pal: Paleta) -> Image.Image:
    """Cartão: contorno arredondado com gradiente iridescente e brilho."""
    W, H = img.size
    mascara = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(caixa, radius=raio, outline=255,
                                              width=max(2, round(2 * s)))
    cor = _gradiente_horizontal(W, H, _iridescente(pal.escuro))
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    camada.paste(cor, (0, 0), mascara)
    return _brilho(img, camada, 5 * s, 0.9 if pal.escuro else 0.5)


@lru_cache(maxsize=8)
def _vinheta(W: int, H: int, cx: float, cy: float, r: float, fundo: str, superficie: str) -> Image.Image:
    """Fundo com o centro um pouco mais claro (profundidade de vidro). Em cache:
    quem usa faz cópia antes de mudar."""
    claro = _misturar(fundo, superficie, 0.9)
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for k in range(24, 0, -1):
        rr_ = r * k / 24
        d.ellipse((cx - rr_, cy - rr_, cx + rr_, cy + rr_),
                  fill=_rgba(_misturar(claro, fundo, k / 24), 1.0))
    return camada


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
    if pal.efeito == "holo":
        if lay.forma == "radial":
            fundo = _vinheta(W, H, cx, cy, r, pal.fundo, pal.superficie).copy()
        else:
            fundo = _vinheta(W, H, W / 2, H * 0.35, max(W, H) * 0.75, pal.fundo, pal.superficie).copy()
        fundo.putalpha(round(255 * opacidade))
    img.paste(fundo, (0, 0), mascara)
    img = _sombra(img, mascara, round(14 * s), 0.28 if pal.escuro else 0.18, round(6 * s))
    d = ImageDraw.Draw(img)
    contorno = _rgba("#FFFFFF" if pal.escuro else "#000000", 0.10)
    if pal.efeito == "holo":
        if lay.forma == "radial":
            img = _anel_holo(img, cx, cy, r - 1.5 * s, s, pal)
        else:
            img = _moldura_holo(img, (margem, margem, W - margem, H - margem), 18 * s, s, pal)
        d = ImageDraw.Draw(img)
    elif lay.forma == "radial":
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
        if pal.efeito == "holo":
            img = _anel_holo_centro(img, cx, cy, cr, s, pal)
            d = ImageDraw.Draw(img)
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


def _anel_holo_centro(img: Image.Image, cx: float, cy: float, cr: float, s: float,
                      pal: Paleta) -> Image.Image:
    return Image.alpha_composite(img, _camada_centro(img.size, cx, cy, cr, s, pal.escuro))


@lru_cache(maxsize=8)
def _camada_centro(tamanho: tuple, cx: float, cy: float, cr: float, s: float, escuro: bool) -> Image.Image:
    W, H = tamanho
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    paradas = _iridescente(escuro)
    for k in range(120):
        d.arc((cx - cr, cy - cr, cx + cr, cy + cr), k * 3 - 90, k * 3 - 86,
              fill=_rgba(_cor_em(paradas, k / 120 + 0.35)), width=max(2, round(1.8 * s)))
    return _com_halo(camada, 4 * s, 0.8 if escuro else 0.45)


def desenhar_item(it, lay: Layout, pal: Paleta, ativo: bool = False,
                  estado: str | None = None) -> tuple[Image.Image, tuple[int, int]]:
    """Uma caixa de formato, já reduzida, e onde colá-la na base."""
    s = SS * lay.escala
    holo = pal.efeito == "holo"
    folga = 7 if holo else 2  # pixels em volta: antisserrilhado (e o brilho, no holográfico)
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
    if holo:
        img = _item_holo(img, (x0, y0, x1, y1), it.raio * SS, s, pal, cor, ativo, estado)
        d = ImageDraw.Draw(img)
        if ativo and estado != "erro":
            preench = _misturar(cor, "#FFFFFF", 0.15)
    else:
        d.rounded_rectangle((x0, y0, x1, y1), radius=it.raio * SS, fill=_rgba(preench),
                            outline=_rgba(borda), width=max(1, round(1.5 * s)))
    rotulo = "Mais…" if it.fmt == MAIS else grp.rotulo(it.fmt)
    rotulo = {"ok": "✓ " + rotulo, "ocupado": "…", "erro": "✕ " + rotulo}.get(estado, rotulo)
    f = fonte(round(13 * s))
    cor_txt = texto_sobre(preench) if (ativo or estado == "erro") else pal.texto
    _texto_centro(d, (x0 + x1) / 2, (y0 + y1) / 2, _encurtar(rotulo, f, (x1 - x0) * 0.9), f, _rgba(cor_txt))
    return img.resize((w, h), Image.LANCZOS), (ox, oy)


def _item_holo(img: Image.Image, caixa: tuple, raio: float, s: float, pal: Paleta, cor: str,
               ativo: bool, estado: str | None) -> Image.Image:
    """Pílula de vidro com contorno neon; destacada = preenchida em gradiente."""
    W, H = img.size
    x0, y0, x1, y1 = caixa
    if estado == "erro":
        cor = "#FF3B30"
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    if ativo or estado == "erro":
        mascara = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mascara).rounded_rectangle(caixa, radius=raio, fill=255)
        grad = _gradiente_horizontal(W, H, [cor, _misturar(cor, "#FFFFFF", 0.3), cor])
        camada.paste(grad, (0, 0), mascara)
        return _brilho(img, camada, 4.5 * s, 1.1 if pal.escuro else 0.7)
    vidro = _rgba(_misturar(pal.superficie, cor, 0.12), 0.78 if pal.escuro else 0.9)
    d.rounded_rectangle(caixa, radius=raio, fill=vidro, outline=_rgba(cor, 0.95),
                        width=max(1, round(1.3 * s)))
    # reflexo: linha clara no topo da pílula, como vidro
    d.line((x0 + raio * 0.8, y0 + 2.2 * s, x1 - raio * 0.8, y0 + 2.2 * s),
           fill=_rgba("#FFFFFF", 0.22 if pal.escuro else 0.6), width=max(1, round(s)))
    contorno = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(contorno).rounded_rectangle(caixa, radius=raio, outline=_rgba(cor, 0.9),
                                               width=max(1, round(1.3 * s)))
    halo = _desfocar(contorno, 3 * s)
    return Image.alpha_composite(Image.alpha_composite(img, halo), camada)


class Pintor:
    """Monta quadros do painel rapidamente: a base é desenhada uma vez e cada
    caixa (normal / destacada / estados) só na primeira vez que aparece."""

    def __init__(self, lay: Layout, pal: Paleta, nome: str, fmt_origem: str, opacidade: float = 0.96,
                 estilo: dict | None = None, fundo_atras: Image.Image | None = None):
        """estilo (forma "vidro"): {"cor": "#RRGGBB", "intensidade": 0–1};
        fundo_atras: captura do que está atrás do painel (vidro de verdade)."""
        self.lay, self.pal = lay, pal
        self.vidro = lay.forma == "vidro"
        self._itens: dict = {}
        if self.vidro:
            from conversor.ui import render_vidro, vidro

            self.estilo = estilo or {"cor": vidro.hex_da_cor(None), "intensidade": vidro.INTENSIDADE_PADRAO}
            self.fundo = render_vidro.preparar_fundo(fundo_atras, self.estilo["intensidade"])
        self._args = (nome, fmt_origem, opacidade)
        self._bases = {False: self._desenhar_base(False)}

    def _desenhar_base(self, centro_ativo: bool) -> Image.Image:
        nome, fmt_origem, opacidade = self._args
        if self.vidro:
            from conversor.ui import render_vidro

            return render_vidro.desenhar_base(self.lay, self.pal, nome, fmt_origem, self.estilo, self.fundo,
                                              centro_ativo)
        return desenhar_base(self.lay, self.pal, nome, fmt_origem, opacidade, centro_ativo=centro_ativo)

    def _base(self, centro_ativo: bool) -> Image.Image:
        if centro_ativo not in self._bases:
            self._bases[centro_ativo] = self._desenhar_base(centro_ativo)
        return self._bases[centro_ativo]

    def _item(self, it, ativo: bool, estado: str | None):
        if self.vidro:
            from conversor.ui import render_vidro

            return render_vidro.desenhar_item(it, self.lay, self.pal, self.estilo, self.fundo, ativo, estado)
        return desenhar_item(it, self.lay, self.pal, ativo, estado)

    def quadro(self, hover: str | None = None, estados: dict | None = None,
               progresso: float = 1.0) -> Image.Image:
        """progresso < 1: animação de entrada (as caixas saem do centro, aparecendo)."""
        estados = estados or {}
        img = self._base(hover == CENTRO).copy()
        p = 1 - (1 - min(1.0, max(0.0, progresso))) ** 3  # desacelera no fim
        for it in self.lay.itens:
            chave = (it.fmt, hover == it.fmt, estados.get(it.fmt))
            if chave not in self._itens:
                self._itens[chave] = self._item(it, chave[1], chave[2])
            tile, pos = self._itens[chave]
            if p < 1:
                dx = (1 - p) * (self.lay.ancora_x - it.x)
                dy = (1 - p) * (self.lay.ancora_y - it.y)
                pos = (round(pos[0] + dx), round(pos[1] + dy))
                tile = tile.copy()
                tile.putalpha(tile.getchannel("A").point(lambda v: round(v * p)))
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
    from conversor.ui import render_vidro

    return saidas + render_vidro.salvar_galeria(pasta)
