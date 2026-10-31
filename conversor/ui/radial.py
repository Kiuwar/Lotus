"""Geometria do painel flutuante (lógica pura, sem janela nem desenho).

Forma "radial": o arquivo fica num círculo no centro (onde está o cursor) e
os formatos ficam em volta, em caixas arredondadas. Cada GRUPO ocupa um arco
próprio, com uma faixa colorida atrás e um rótulo, separado dos outros por um
espaço: Imagem de um lado, Documento de outro, e assim por diante.

Forma "cartao": lista em cartão, com uma seção por grupo.

Forma "vidro": só o ícone do arquivo no centro e uma PÍLULA por formato em
volta (órbita), sem fundo nem faixas; dois anéis intercalados quando há mais
de 10 formatos. A largura de cada pílula acompanha o texto.

Tudo em pixels da janela; `escala` vem do tamanho P/M/G.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MAX_ITENS = 12   # acima disso, os últimos vão para "Mais…"
MAX_ITENS_VIDRO = 18
UM_ANEL_VIDRO = 10
MAIS = "__mais__"
CENTRO = "__centro__"


@dataclass(frozen=True)
class Item:
    fmt: str          # formato de destino, ou MAIS
    grupo: str | None
    x: float          # centro da caixa
    y: float
    w: float
    h: float
    raio: float       # arredondamento dos cantos

    def contem(self, px: float, py: float) -> bool:
        return abs(px - self.x) <= self.w / 2 and abs(py - self.y) <= self.h / 2


@dataclass(frozen=True)
class Faixa:
    """Arco colorido atrás das caixas de um grupo (só na forma radial)."""

    grupo: str
    ang_ini: float    # graus, 0 = direita, sentido horário (y para baixo)
    ang_fim: float
    r_int: float
    r_ext: float
    rotulo_x: float   # centro do rótulo do grupo (acompanha a curva do anel)
    rotulo_y: float
    rotulo_ang: float  # graus, ângulo do centro do arco


@dataclass
class Layout:
    forma: str
    largura: int
    altura: int
    ancora_x: float   # ponto do layout que fica sob o cursor
    ancora_y: float
    itens: list[Item] = field(default_factory=list)
    faixas: list[Faixa] = field(default_factory=list)
    centro_r: float = 0.0          # radial: raio do círculo central
    fundo_r: float = 0.0           # radial: raio do disco de fundo
    secoes: list[tuple[str, float]] = field(default_factory=list)  # cartão: (grupo, y do título)
    escala: float = 1.0
    margem: float = 0.0            # cartão: espaço transparente em volta (sombra)

    def hit_test(self, px: float, py: float) -> str | None:
        for it in self.itens:
            if it.contem(px, py):
                return it.fmt
        if self.forma in ("radial", "vidro"):
            d = math.hypot(px - self.ancora_x, py - self.ancora_y)
            if d <= self.centro_r:
                return CENTRO
        return None


def _limitar(grupos: list[tuple[str, list[str]]],
             maximo: int = MAX_ITENS) -> tuple[list[tuple[str, list[str]]], bool]:
    total = sum(len(f) for _, f in grupos)
    if total <= maximo:
        return grupos, False
    # Uma vaga fica para "Mais…"; as outras são divididas em rodízio entre os
    # grupos (um de cada vez), para nenhum grupo sumir inteiro no "Mais…".
    restam = maximo - 1
    quantos = [0] * len(grupos)
    while restam > 0:
        avancou = False
        for i, (_g, fs) in enumerate(grupos):
            if restam > 0 and quantos[i] < len(fs):
                quantos[i] += 1
                restam -= 1
                avancou = True
        if not avancou:
            break
    return [(g, fs[:k]) for (g, fs), k in zip(grupos, quantos) if k], True


def _angulos(grupos, tem_mais: bool, passo: float, lacuna: float) -> list[float]:
    """Ângulo (graus) do centro de cada caixa, na mesma ordem do desenho."""
    ang = -90.0 + (lacuna * passo / 2 if lacuna else 0)
    saida = []
    for _g, fmts in list(grupos) + ([(None, [MAIS])] if tem_mais else []):
        for _f in fmts:
            saida.append(ang + passo / 2)
            ang += passo
        ang += lacuna * passo
    return saida


def radial(grupos: list[tuple[str, list[str]]], escala: float = 1.0) -> Layout:
    grupos, tem_mais = _limitar(grupos)
    w, h, raio = 60 * escala, 42 * escala, 14 * escala
    centro_r = 46 * escala
    n = sum(len(f) for _, f in grupos) + (1 if tem_mais else 0)
    n_lacunas = len(grupos) + (1 if tem_mais else 0)
    lacuna = 0.7 if n_lacunas > 1 else 0.0   # espaço entre grupos, em "vagas"
    vagas = max(n + lacuna * n_lacunas, 1)
    passo = 360.0 / vagas
    # Raio do anel: caixas vizinhas não se encostam e não invadem o centro.
    corda_min = w + 10 * escala
    r_vizinho = (corda_min / 2) / math.sin(math.radians(min(passo, 179) / 2))
    r_anel = max(100 * escala, centro_r + h / 2 + 18 * escala, r_vizinho if n > 1 else 0)
    # A corda mínima só vale na horizontal; na diagonal (~30°) duas caixas
    # podem se sobrepor mesmo assim. Cresce o anel até nenhum par se tocar.
    angulos = _angulos(grupos, tem_mais, passo, lacuna)
    folga = 6 * escala
    for _ in range(60):
        pts = [(r_anel * math.cos(math.radians(a)), r_anel * math.sin(math.radians(a))) for a in angulos]
        if not any(abs(p[0] - q[0]) < w + folga and abs(p[1] - q[1]) < h + folga
                   for i, p in enumerate(pts) for q in pts[i + 1:]):
            break
        r_anel *= 1.03
    r_int, r_ext = r_anel - h / 2 - 7 * escala, r_anel + h / 2 + 7 * escala
    r_rot = r_ext + 11 * escala                # rótulos ficam DENTRO do disco
    fundo_r = r_ext + 22 * escala
    meio = math.ceil(fundo_r + 18 * escala)   # margem para a sombra
    lado = 2 * meio
    cx = cy = meio

    itens, faixas = [], []
    ang = -90.0 + (lacuna * passo / 2 if lacuna else 0)  # começa no topo
    blocos = list(grupos) + ([(None, [MAIS])] if tem_mais else [])
    for g, fmts in blocos:
        inicio = ang
        for f in fmts:
            meio_vaga = ang + passo / 2
            rad = math.radians(meio_vaga)
            itens.append(Item(f, g, cx + r_anel * math.cos(rad), cy + r_anel * math.sin(rad), w, h, raio))
            ang += passo
        if g is not None:
            meio_ang = (inicio + ang) / 2
            rad = math.radians(meio_ang)
            faixas.append(Faixa(g, inicio + passo * 0.12, ang - passo * 0.12, r_int, r_ext,
                                cx + r_rot * math.cos(rad), cy + r_rot * math.sin(rad), meio_ang))
        ang += lacuna * passo
    return Layout("radial", lado, lado, cx, cy, itens, faixas, centro_r, fundo_r, escala=escala)


def cartao(grupos: list[tuple[str, list[str]]], escala: float = 1.0) -> Layout:
    m = 18 * escala                      # margem transparente para a sombra
    pad, gap = 16 * escala, 8 * escala   # dentro do cartão
    w, h, raio = 62 * escala, 34 * escala, 10 * escala
    por_linha = 4
    largura = math.ceil(2 * m + 2 * pad + por_linha * w + (por_linha - 1) * gap)
    y = m + 64 * escala  # cabeçalho: ícone + nome do arquivo
    itens, secoes = [], []
    for g, fmts in grupos:
        secoes.append((g, y))
        y += 22 * escala
        for i, f in enumerate(fmts):
            col, lin = i % por_linha, i // por_linha
            itens.append(Item(f, g, m + pad + w / 2 + col * (w + gap), y + h / 2 + lin * (h + gap), w, h, raio))
        y += math.ceil(len(fmts) / por_linha) * (h + gap) + 6 * escala
    altura = math.ceil(y + pad - gap + m)
    # O cursor fica um pouco acima/à esquerda do canto do cartão (como um menu).
    return Layout("cartao", largura, altura, m - 12 * escala, m - 12 * escala, itens,
                  secoes=secoes, escala=escala, margem=m)


def largura_pilula(rotulo: str, escala: float = 1.0) -> float:
    """Largura de uma pílula de vidro: acompanha o texto (estimativa por letra)."""
    return max(62.0, 34.0 + 9.6 * len(rotulo)) * escala  # inclui o pontinho de cor


def orbita(grupos: list[tuple[str, list[str]]], escala: float = 1.0) -> Layout:
    from conversor.ui.grupos import rotulo as rotulo_de

    grupos, tem_mais = _limitar(grupos, MAX_ITENS_VIDRO)
    seq = [(g, f) for g, fs in grupos for f in fs] + ([(None, MAIS)] if tem_mais else [])
    h, raio = 34 * escala, 17 * escala
    centro_r = 34 * escala
    folga = 8 * escala
    larguras = [largura_pilula("Mais…" if f == MAIS else rotulo_de(f), escala) for _, f in seq]
    n = len(seq)
    if n > UM_ANEL_VIDRO:  # dois anéis intercalados: dentro os pares, fora os ímpares
        aneis = [list(range(0, n, 2)), list(range(1, n, 2))]
    else:
        aneis = [list(range(n))]
    angulos = [0.0] * n
    for k, anel in enumerate(aneis):
        passo = 360.0 / max(len(anel), 1)
        for j, i in enumerate(anel):
            angulos[i] = -90.0 + j * passo + (passo / 2 if k == 1 else 0.0)
    # Raio mínimo: as pílulas do anel interno não tocam o disco central nem o
    # nome do arquivo (que fica logo abaixo dele).
    r_in = centro_r + h / 2 + 30 * escala + max(larguras, default=0) * 0.25
    for _ in range(120):
        r_out = r_in + h + 12 * escala
        raios = [r_in if (len(aneis) == 1 or i in aneis[0]) else r_out for i in range(n)]
        pts = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for r, a in zip(raios, angulos)]
        sobrepoe = any(abs(p[0] - q[0]) < (larguras[i] + larguras[j]) / 2 + folga and abs(p[1] - q[1]) < h + folga
                       for i, p in enumerate(pts) for j, q in enumerate(pts) if j > i)
        if not sobrepoe:
            break
        r_in *= 1.04
    ext_x = max((abs(p[0]) + larguras[i] / 2 for i, p in enumerate(pts)), default=centro_r)
    ext_y = max((abs(p[1]) + h / 2 for p in pts), default=centro_r)
    meio = math.ceil(max(ext_x, ext_y, centro_r + 30 * escala) + 22 * escala)  # margem: sombra/brilho
    cx = cy = meio
    itens = [Item(f, g, cx + p[0], cy + p[1], larguras[i], h, raio) for i, ((g, f), p) in enumerate(zip(seq, pts))]
    return Layout("vidro", 2 * meio, 2 * meio, cx, cy, itens, centro_r=centro_r, escala=escala)


def montar(grupos: list[tuple[str, list[str]]], forma: str = "radial", escala: float = 1.0) -> Layout:
    if forma == "cartao":
        return cartao(grupos, escala)
    if forma == "vidro":
        return orbita(grupos, escala)
    return radial(grupos, escala)


def posicionar(lay: Layout, cursor_x: int, cursor_y: int, tela_l: int, tela_a: int) -> tuple[int, int]:
    """Canto superior esquerdo da janela: âncora no cursor, sem sair da tela."""
    x = round(cursor_x - lay.ancora_x)
    y = round(cursor_y - lay.ancora_y)
    x = min(max(0, x), max(0, tela_l - lay.largura))
    y = min(max(0, y), max(0, tela_a - lay.altura))
    return x, y
