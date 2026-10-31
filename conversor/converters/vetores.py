"""Desenhos vetoriais: SVG e DXF (corte a laser, plotter, logotipos para 3D).

- SVG → PNG/JPG/WEBP: resvg (resvg-py, MIT). Sempre com dpi=96 explícito: com
  o padrão (0) um SVG medido em mm dá "tamanho inválido" (visto ao testar).
- SVG → PDF vetorial: svglib + reportlab (LGPL-3 / BSD). Imagens externas só
  de caminhos locais relativos; sem rede e sem entidades XML (regra 8).
- SVG → STL/3MF: as áreas PREENCHIDAS viram peça com espessura (extrusão);
  furos pela regra par/ímpar; medida real do SVG (1 px = 25,4/96 mm).
- SVG ↔ DXF: linhas, polilinhas, arcos, círculos, elipses e curvas, em mm.

Leitura dos caminhos do SVG: svgelements (MIT). Polígonos: shapely (BSD).
"""

from __future__ import annotations

import math
from pathlib import Path

from conversor.core.engine import ConversionError
from conversor.core.registry import register

PX_MM = 25.4 / 96  # 1 px CSS = 1/96 polegada
ESPESSURA_PADRAO = 2.0  # mm
PASSOS_CURVA = 24       # pontos por trecho curvo


def _avisar(options: dict, texto: str) -> None:
    avisos = options.setdefault("_warnings", [])
    if texto not in avisos:
        avisos.append(texto)


# ---------- leitura do SVG em contornos (mm) ----------

def contornos_svg(src: Path) -> list[dict]:
    """Cada forma: {"aneis": [[(x, y) mm, …], …], "preenchida": bool}. Y para
    cima (como numa peça vista de cima), já em milímetros."""
    import numpy as np
    import svgelements as se

    try:
        svg = se.SVG.parse(str(src), reify=True)
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"{src.name} não pôde ser lido como SVG ({e}).") from e
    formas = []
    for el in svg.elements():
        if not isinstance(el, se.Shape):
            continue
        try:
            caminho = se.Path(el)
        except Exception:  # noqa: BLE001 - forma degenerada
            continue
        aneis = []
        for sub in caminho.as_subpaths():
            pts: list[tuple[float, float]] = []
            for seg in se.Path(sub):
                if isinstance(seg, (se.Move, se.Line, se.Close)):
                    if seg.end is not None:
                        pts.append((seg.end.x, seg.end.y))
                elif seg.start is not None:
                    pts.extend((float(x), float(y)) for x, y in seg.npoint(np.linspace(0, 1, PASSOS_CURVA + 1))[1:])
            limpos = []
            for x, y in pts:
                ponto = (x * PX_MM, -y * PX_MM)
                if not limpos or math.dist(limpos[-1], ponto) > 1e-6:
                    limpos.append(ponto)
            if len(limpos) >= 2:
                aneis.append(limpos)
        if aneis:
            preenchida = el.fill is not None and el.fill.value is not None and el.fill.alpha != 0
            formas.append({"aneis": aneis, "preenchida": preenchida})
    return formas


def _area_preenchida(formas: list[dict], options: dict, nome: str):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    partes = []
    so_linha = 0
    for f in formas:
        if not f["preenchida"]:
            so_linha += 1
            continue
        geo = None
        for anel in f["aneis"]:
            if len(anel) < 3:
                continue
            p = Polygon(anel).buffer(0)
            if p.is_empty:
                continue
            geo = p if geo is None else geo.symmetric_difference(p)  # regra par/ímpar: furos
        if geo is not None and not geo.is_empty:
            partes.append(geo)
    if so_linha:
        _avisar(options, f"{nome}: {so_linha} forma(s) só com contorno (sem preenchimento) foram "
                         "ignoradas na peça 3D. Como resolver: preencha-as no editor de SVG.")
    if not partes:
        raise ConversionError(f"{nome} não tem áreas preenchidas para virar peça 3D.")
    return unary_union(partes)


@register(["svg"], ["stl", "3mf"], category="3D",
          notes="Áreas preenchidas viram peça com espessura (padrão 2 mm); medidas reais do SVG.")
def svg_para_peca(src: Path, dst: Path, options: dict) -> None:
    import trimesh

    from conversor.converters.modelos3d import gravar_malha

    from shapely import affinity

    area = _area_preenchida(contornos_svg(src), options, src.name)
    espessura = float(options.get("espessura") or ESPESSURA_PADRAO)
    largura = options.get("largura")
    if largura:  # escala só o desenho (X e Y); a espessura fica como pedida
        x0, _, x1, _ = area.bounds
        fator = float(largura) / max(x1 - x0, 1e-9)
        area = affinity.scale(area, xfact=fator, yfact=fator, origin=(0, 0))
    poligonos = list(getattr(area, "geoms", [area]))
    pecas = [trimesh.creation.extrude_polygon(p, espessura) for p in poligonos if p.area > 1e-6]
    malha = trimesh.util.concatenate(pecas)
    malha.apply_translation(-malha.bounds[0])  # canto na origem, apoiada na mesa
    malha.units = "millimeters"
    gravar_malha(malha, dst, dst.suffix.lstrip(".").lower(), options)


# ---------- SVG → imagem e PDF ----------

def _png_do_svg(src: Path, largura_px: int | None = None) -> bytes:
    import resvg_py

    try:
        kw = {"svg_path": str(src), "dpi": 96.0}
        if largura_px:
            kw["width"] = int(largura_px)
        return bytes(resvg_py.svg_to_bytes(**kw))
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"{src.name} não pôde ser desenhado ({e}).") from e


@register(["svg"], ["png", "jpg", "webp"], category="Imagem",
          notes="Desenho do SVG em imagem (largura mínima de 1000 pixels).")
def svg_para_imagem(src: Path, dst: Path, options: dict) -> None:
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(_png_do_svg(src)))
    if img.width < 1000:  # SVG pequeno (ex.: ícone de 24 px): desenha maior, sem serrilhado
        img = Image.open(io.BytesIO(_png_do_svg(src, 1000)))
    img.load()
    alvo = dst.suffix.lstrip(".").lower()
    if alvo == "jpg":
        if img.mode in ("RGBA", "LA"):
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            fundo.paste(img, mask=img.getchannel("A"))
            img = fundo
            _avisar(options, f"{src.name}: transparência substituída por fundo branco (JPG não "
                             "tem transparência).")
        img.convert("RGB").save(dst, format="JPEG", quality=int(options.get("quality", 90)))
    else:
        img.save(dst, format="WEBP" if alvo == "webp" else "PNG")


@register(["svg"], ["pdf"], category="Documento", notes="PDF vetorial, no tamanho do desenho.")
def svg_para_pdf(src: Path, dst: Path, options: dict) -> None:
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg

    try:
        desenho = svg2rlg(str(src))
    except Exception as e:  # noqa: BLE001
        desenho = None
        motivo = str(e)
    else:
        motivo = "conteúdo não suportado"
    if desenho is None:
        raise ConversionError(f"{src.name} não pôde ser convertido para PDF ({motivo}).")
    renderPDF.drawToFile(desenho, str(dst))
    _avisar(options, "SVG → PDF: filtros, máscaras e algumas fontes podem sair diferentes; confira.")


# ---------- SVG ↔ DXF ----------

def _ezdxf():
    import ezdxf

    return ezdxf


@register(["svg"], ["dxf"], category="3D",
          notes="Contornos em milímetros (corte a laser/CNC); cores e preenchimento não.")
def svg_para_dxf(src: Path, dst: Path, options: dict) -> None:
    ezdxf = _ezdxf()
    formas = contornos_svg(src)
    if not formas:
        raise ConversionError(f"{src.name} não tem formas para exportar.")
    doc = ezdxf.new(units=4)  # 4 = milímetros (INSUNITS); o padrão do ezdxf é metros
    msp = doc.modelspace()
    for f in formas:
        for anel in f["aneis"]:
            fechado = math.dist(anel[0], anel[-1]) < 1e-6
            pts = anel[:-1] if fechado and len(anel) > 2 else anel
            msp.add_lwpolyline(pts, format="xy", close=fechado)
    doc.saveas(str(dst))
    _avisar(options, "DXF guarda só os contornos: cores, preenchimentos e textos do SVG não.")


TIPOS_DXF = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"}
FATOR_DXF_MM = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 13: 0.001, 14: 0.1}


def contornos_dxf(src: Path, options: dict) -> list[list[tuple[float, float]]]:
    ezdxf = _ezdxf()
    import ezdxf.path as caminhos

    try:
        doc = ezdxf.readfile(str(src))
    except Exception as e:  # noqa: BLE001
        raise ConversionError(f"{src.name} não pôde ser lido como DXF ({e}).") from e
    fator = FATOR_DXF_MM.get(int(doc.units or 0), 1.0)
    linhas, ignorados = [], {}
    for e in doc.modelspace():
        tipo = e.dxftype()
        if tipo not in TIPOS_DXF:
            ignorados[tipo] = ignorados.get(tipo, 0) + 1
            continue
        try:
            pts = [(v.x * fator, v.y * fator) for v in caminhos.make_path(e).flattening(0.02)]
        except Exception:  # noqa: BLE001
            ignorados[tipo] = ignorados.get(tipo, 0) + 1
            continue
        if len(pts) >= 2:
            linhas.append(pts)
    if ignorados:
        lista = ", ".join(f"{n} {t}" for t, n in sorted(ignorados.items()))
        _avisar(options, f"{src.name}: elementos não convertidos (textos, cotas, blocos…): {lista}.")
    if not linhas:
        raise ConversionError(f"{src.name} não tem linhas, arcos ou círculos para converter.")
    return linhas


@register(["dxf"], ["svg"], category="Imagem", notes="Linhas, arcos e círculos, em milímetros.")
def dxf_para_svg(src: Path, dst: Path, options: dict) -> None:
    linhas = contornos_dxf(src, options)
    xs = [x for l in linhas for x, _ in l]
    ys = [y for l in linhas for _, y in l]
    x0, y1 = min(xs), max(ys)
    larg, alt = max(max(xs) - x0, 1e-3), max(y1 - min(ys), 1e-3)
    margem = max(larg, alt) * 0.02
    caminhos = []
    for l in linhas:  # Y do DXF cresce para cima; no SVG, para baixo
        pts = " ".join(f"{x - x0 + margem:.4f},{y1 - y + margem:.4f}" for x, y in l)
        caminhos.append(f'<polyline points="{pts}"/>')
    w, h = larg + 2 * margem, alt + 2 * margem
    Path(dst).write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.4f}mm" height="{h:.4f}mm" '
        f'viewBox="0 0 {w:.4f} {h:.4f}">\n'
        f'<g fill="none" stroke="#000000" stroke-width="{max(w, h) / 500:.4f}" '
        'stroke-linecap="round" stroke-linejoin="round">\n' + "\n".join(caminhos) + "\n</g>\n</svg>\n",
        encoding="utf-8")
