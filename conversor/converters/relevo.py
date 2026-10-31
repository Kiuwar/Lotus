"""Imagem → STL/3MF: litofania (padrão) ou relevo.

Litofania: placa fina que mostra a foto contra a luz — onde a imagem é ESCURA
a placa é GROSSA (passa menos luz). Relevo (`--modo relevo`): o contrário,
claro = alto (carimbos, mapas de altura).

Padrões (mm): largura 100, espessura de 0,8 a 3,0, um ponto a cada 0,2 mm
(mais fino que isso o bico de 0,4 mm não reproduz). A malha é FECHADA
(topo em relevo, fundo plano e quatro paredes), pronta para o fatiador.
"""

from __future__ import annotations

from pathlib import Path

from conversor.converters.images import IMAGES, avif_disponivel, heic_disponivel
from conversor.core.engine import ConversionError
from conversor.core.registry import register

LARGURA_PADRAO = 100.0
ESP_MIN, ESP_MAX = 0.8, 3.0
PASSO = 0.2  # mm entre pontos da malha
NOTA = "Litofania: escuro = mais grosso (100 mm de largura, 0,8–3,0 mm); veja contra a luz."


def malha_relevo(alturas, passo: float):
    """Malha fechada a partir de uma grade de alturas (linhas = Y de cima para baixo)."""
    import numpy as np
    import trimesh

    a = np.asarray(alturas, dtype=float)
    ny, nx = a.shape
    xs = np.arange(nx) * passo
    ys = (ny - 1 - np.arange(ny)) * passo  # 1ª linha da imagem no alto (Y maior)
    gx, gy = np.meshgrid(xs, ys)
    topo = np.column_stack([gx.ravel(), gy.ravel(), a.ravel()])
    base = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(nx * ny)])
    vertices = np.vstack([topo, base])
    n = nx * ny
    idx = np.arange(n).reshape(ny, nx)
    a00, a01, a10, a11 = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    # Topo voltado para cima (+Z); base para baixo. Y diminui com a linha da imagem.
    topo_f = np.vstack([np.column_stack([a00, a10, a01]), np.column_stack([a01, a10, a11])])
    base_f = topo_f[:, ::-1] + n
    paredes = []
    borda = [idx[0, :], idx[:, -1], idx[-1, ::-1], idx[::-1, 0]]  # contorno em volta
    for linha in borda:
        t0, t1 = linha[:-1], linha[1:]
        b0, b1 = t0 + n, t1 + n
        paredes.append(np.column_stack([t0, t1, b1]))
        paredes.append(np.column_stack([t0, b1, b0]))
    faces = np.vstack([topo_f, base_f, *paredes])
    malha = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    if malha.volume < 0:
        malha.invert()
    return malha


@register(IMAGES, ["stl", "3mf"], category="3D", notes=NOTA)
def imagem_para_relevo(src: Path, dst: Path, options: dict) -> None:
    import numpy as np
    from PIL import Image

    from conversor.converters.images import _open
    from conversor.converters.modelos3d import gravar_malha

    origem = options.get("_source_format") or src.suffix.lstrip(".").lower()
    if origem == "heic":
        from conversor.converters.images import _heic_pronto

        _heic_pronto()
    img = _open(src, options)
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        img = fundo
        options.setdefault("_warnings", []).append(
            f"{src.name}: partes transparentes viraram branco (a parte mais fina da peça).")
    cinza = img.convert("L")
    largura = float(options.get("largura") or LARGURA_PADRAO)
    esp_min = float(options.get("espessura_min") or ESP_MIN)
    esp_max = float(options.get("espessura") or ESP_MAX)
    if not 0 < esp_min < esp_max:
        raise ConversionError("A espessura máxima precisa ser maior que a mínima.")
    nx = max(2, int(round(largura / PASSO)) + 1)
    ny = max(2, int(round(nx * cinza.height / cinza.width)))
    passo = largura / (nx - 1)
    cinza = cinza.resize((nx, ny), Image.LANCZOS)
    claro = np.asarray(cinza, dtype=float) / 255.0
    escuro = 1.0 - claro
    fracao = claro if options.get("modo") == "relevo" else escuro
    alturas = esp_min + fracao * (esp_max - esp_min)
    malha = malha_relevo(alturas, passo)
    malha.units = "millimeters"
    gravar_malha(malha, dst, dst.suffix.lstrip(".").lower(), options)


register(["avif"], ["stl", "3mf"], category="3D", notes=NOTA, available=avif_disponivel)(imagem_para_relevo)
register(["heic"], ["stl", "3mf"], category="3D", notes=NOTA, available=heic_disponivel)(imagem_para_relevo)
