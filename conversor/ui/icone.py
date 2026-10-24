"""Ícone do Lotus: uma flor de lótus desenhada por código (sem imagem externa).

Desenho em 4× e reduzido (bordas lisas). Pétalas em degradê rosa → lilás,
miolo dourado e uma folha verde estilizada embaixo. Em tamanhos pequenos
(≤ 32 px) as pétalas ficam mais grossas e o contorno mais forte, para o
ícone continuar legível na barra de tarefas e ao lado do relógio.

`scripts/gerar_icone.py` grava os arquivos em conversor/recursos/
(lotus.ico, lotus.icns, lotus.png); o teste confere que estão atualizados.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
TAMANHOS_ICO = [16, 20, 24, 32, 40, 48, 64, 128, 256]

ROSA_CLARO = (255, 214, 232)
ROSA = (240, 98, 160)
LILAS = (156, 84, 214)
OURO = (255, 196, 64)
VERDE = (46, 160, 120)
VERDE_ESCURO = (24, 110, 84)


def _petala(lado: int, cx: float, base_y: float, comprimento: float, largura: float,
            angulo: float) -> tuple[Image.Image, list[tuple[float, float]]]:
    """Máscara de uma pétala pontuda (duas curvas) girada em torno da base,
    e o contorno (para desenhar a borda)."""
    pontos = []
    n = 60
    for i in range(n + 1):  # lado direito, da base à ponta
        t = i / n
        x = largura / 2 * math.sin(math.pi * t) ** 0.9
        y = -comprimento * t
        pontos.append((x, y))
    for i in range(n, -1, -1):  # lado esquerdo, da ponta à base
        t = i / n
        x = -largura / 2 * math.sin(math.pi * t) ** 0.9
        y = -comprimento * t
        pontos.append((x, y))
    a = math.radians(angulo)
    girados = [(cx + x * math.cos(a) - y * math.sin(a), base_y + x * math.sin(a) + y * math.cos(a))
               for x, y in pontos]
    m = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(m).polygon(girados, fill=255)
    return m, girados


def _degrade(lado: int, topo: tuple, base: tuple) -> Image.Image:
    """Degradê vertical (topo → base)."""
    col = Image.new("RGB", (1, lado))
    for y in range(lado):
        f = y / max(1, lado - 1)
        col.putpixel((0, y), tuple(round(topo[i] + (base[i] - topo[i]) * f) for i in range(3)))
    return col.resize((lado, lado))


def desenhar_lotus(tamanho: int, fundo: bool = False) -> Image.Image:
    """Ícone RGBA de `tamanho`×`tamanho`. `fundo=True`: quadrado arredondado
    claro atrás (estilo de ícone do Mac)."""
    escala = 4
    L = tamanho * escala
    pequeno = tamanho <= 32
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))

    if fundo:
        raio = round(L * 0.225)
        margem = round(L * 0.06)
        base = Image.new("L", (L, L), 0)
        ImageDraw.Draw(base).rounded_rectangle((margem, margem, L - margem, L - margem), raio, fill=255)
        sombra = base.filter(ImageFilter.GaussianBlur(L * 0.02))
        img.paste((0, 0, 0, 60), (0, round(L * 0.01)), sombra)
        img.paste(Image.composite(_degrade(L, (255, 250, 252), (243, 232, 250)), img.convert("RGB"), base)
                  .convert("RGBA"), (0, 0), base)

    # Área útil da flor (com fundo, um pouco menor).
    # Em tamanhos pequenos a flor ocupa mais do quadro (legível em 16 px).
    k = 0.78 if fundo else (1.12 if pequeno else 1.0)
    cx = L / 2
    base_y = L * (0.5 + 0.22 * k)
    comp = L * 0.46 * k
    larg = L * (0.25 if pequeno else 0.21) * k

    # Folha / água embaixo.
    folha = Image.new("L", (L, L), 0)
    fy = base_y + L * 0.035 * k
    ImageDraw.Draw(folha).ellipse((cx - L * 0.40 * k, fy - L * 0.06 * k, cx + L * 0.40 * k, fy + L * 0.07 * k),
                                  fill=255)
    img.paste(Image.composite(_degrade(L, VERDE, VERDE_ESCURO), Image.new("RGB", (L, L)), folha)
              .convert("RGBA"), (0, 0), folha)

    contorno = (120, 40, 110, 255)
    espessura = max(1, round(L * (0.018 if pequeno else 0.008)))
    # De trás para a frente: laterais abertas, intermediárias, central.
    camadas = [(-78, 0.70, ROSA_CLARO, ROSA), (78, 0.70, ROSA_CLARO, ROSA),
               (-50, 0.88, ROSA_CLARO, ROSA), (50, 0.88, ROSA_CLARO, ROSA),
               (-24, 0.98, (255, 226, 240), LILAS), (24, 0.98, (255, 226, 240), LILAS),
               (0, 1.0, (255, 236, 246), LILAS)]
    if pequeno:  # menos pétalas: legível em 16 px
        camadas = [c for c in camadas if abs(c[0]) != 24]
    desenho = ImageDraw.Draw(img)
    degrades: dict[tuple, Image.Image] = {}
    for angulo, fator, topo, baixo in camadas:
        m, pontos = _petala(L, cx, base_y, comp * fator, larg, angulo)
        # Linha grossa no contorno; o preenchimento por cima cobre a metade
        # interna e sobra a borda (rápido mesmo em 4096 px).
        desenho.line(pontos + [pontos[0]], fill=contorno, width=espessura * 2, joint="curve")
        if (topo, baixo) not in degrades:
            degrades[(topo, baixo)] = _degrade(L, topo, baixo).convert("RGBA")
        img.paste(degrades[(topo, baixo)], (0, 0), m)

    # Miolo dourado.
    r = L * (0.05 if pequeno else 0.04) * k
    my = base_y - L * 0.03 * k
    ImageDraw.Draw(img).ellipse((cx - r, my - r, cx + r, my + r), fill=OURO + (255,))

    return img.resize((tamanho, tamanho), Image.LANCZOS)


def gerar(destino: Path = RECURSOS) -> dict[str, Path]:
    """Grava lotus.ico (Windows), lotus.icns (Mac) e lotus.png (janela/bandeja)."""
    destino.mkdir(parents=True, exist_ok=True)
    ico = destino / "lotus.ico"
    icns = destino / "lotus.icns"
    png = destino / "lotus.png"
    grande = desenhar_lotus(256)
    imagens = [desenhar_lotus(t) for t in TAMANHOS_ICO]
    grande.save(ico, format="ICO", sizes=[(t, t) for t in TAMANHOS_ICO], append_images=imagens[:-1])
    desenhar_lotus(1024, fundo=True).save(icns, format="ICNS")
    desenhar_lotus(512).save(png, format="PNG")
    return {"ico": ico, "icns": icns, "png": png}


def caminho(nome: str) -> Path:
    """Arquivo de ícone no app (rodando do código ou empacotado pelo PyInstaller)."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", "")) / "conversor" / "recursos"
    return base / nome if base.is_dir() else RECURSOS / nome


def aplicar_icone(root) -> None:
    """Ícone da flor na janela e na barra de tarefas/Dock. Falha só vai ao log."""
    import sys

    try:
        if sys.platform == "win32":
            root.iconbitmap(default=str(caminho("lotus.ico")))
        else:
            import tkinter as tk

            foto = tk.PhotoImage(master=root, file=str(caminho("lotus.png")))
            root.iconphoto(True, foto)
            root._lotus_icone = foto  # mantém a imagem viva
    except Exception:  # noqa: BLE001 - ícone nunca pode impedir o app de abrir
        from conversor.logs import get_logger

        get_logger().exception("não foi possível aplicar o ícone")
