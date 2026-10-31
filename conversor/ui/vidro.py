"""Estilo "Vidro" (glassmorphism, como os botões de vidro do iPhone): lógica pura.

Cores do vidro, o que a "intensidade" muda (desfoque e opacidade) e o ajuste
de contraste: a tinta de cada pílula fica mais opaca até o texto ter contraste
suficiente sobre o fundo REAL, então um papel de parede claro ou cheio de
detalhes não apaga o texto. Regra 18: texto escuro >= 4,5:1; texto BRANCO sobre
vidro colorido >= 3:1 (a mesma exceção dos botões coloridos do macOS,
`tema.texto_sobre`), que é o visual da referência.
"""

from __future__ import annotations

from conversor.ui.tema import contraste, luminancia

# Azul tirado da referência enviada (botão de vidro azul); as outras seguem a mesma luz.
CORES = {
    "Azul": "#3D8FEB",
    "Neutro": "#F2F4F8",
    "Rosa": "#E24E8C",
    "Verde": "#1E9A60",
    "Roxo": "#8A63F2",
    "Grafite": "#3A3F4B",
}
COR_PADRAO = "Azul"
INTENSIDADE_PADRAO = 0.6
TEXTO_CLARO, TEXTO_ESCURO = "#FFFFFF", "#1D1D1F"


def hex_da_cor(nome_ou_hex: str | None) -> str:
    if nome_ou_hex and nome_ou_hex.startswith("#"):
        return nome_ou_hex
    return CORES.get(nome_ou_hex or COR_PADRAO, CORES[COR_PADRAO])


def parametros(intensidade: float) -> dict:
    """intensidade 0 = vidro limpo (mais transparente), 1 = vidro bem fosco."""
    i = min(1.0, max(0.0, float(intensidade)))
    return {"desfoque": 4 + 20 * i,          # px (1×) no fundo capturado
            "alfa_tinta": 0.28 + 0.27 * i,   # opacidade mínima da cor
            "nevoa": 0.05 + 0.12 * i}        # véu branco do vidro fosco


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _hex(c) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in c[:3])


def misturar(fundo: tuple, cor: str, alfa: float, nevoa: float = 0.0) -> str:
    """Cor resultante: fundo, depois o véu branco, depois a tinta com `alfa`."""
    f = [v + (255 - v) * nevoa for v in fundo[:3]]
    t = _rgb(cor)
    return _hex([f[i] + (t[i] - f[i]) * alfa for i in range(3)])


MINIMO = {TEXTO_CLARO: 3.0, TEXTO_ESCURO: 4.5}


def texto_preferido(cor: str) -> str:
    """Vidro colorido/escuro: texto branco; vidro claro (Neutro): texto escuro."""
    return TEXTO_ESCURO if luminancia(cor) > 0.5 else TEXTO_CLARO


def tinta_legivel(fundos: list[tuple], cor: str, alfa_min: float,
                  nevoa: float = 0.0) -> tuple[float, str]:
    """(alfa da tinta, cor do texto) com contraste mínimo (MINIMO) sobre TODOS
    os `fundos` (cores RGB por baixo da pílula). Sobe o alfa de 0,05 em 0,05."""
    preferido = texto_preferido(cor)
    outro = TEXTO_ESCURO if preferido == TEXTO_CLARO else TEXTO_CLARO
    passos = [alfa_min]
    while passos[-1] < 1.0:
        passos.append(min(1.0, round(passos[-1] + 0.05, 4)))

    def serve(texto: str, alfa: float) -> bool:
        return all(contraste(texto, misturar(f, cor, alfa, nevoa)) >= MINIMO[texto] for f in fundos)

    # 1º o texto que combina com a cor (branco no vidro colorido, como a
    # referência), engrossando a tinta; só se nem opaca der, o outro.
    for texto in (preferido, outro):
        for alfa in passos:
            if serve(texto, alfa):
                return alfa, texto
    # Cor livre sem contraste possível: o mais legível dos dois, com a tinta cheia.
    melhor = max((preferido, outro),
                 key=lambda t: min(contraste(t, misturar(f, cor, 1.0, nevoa)) for f in fundos))
    return 1.0, melhor


# Sem fundo capturado (Mac, ou falha na captura): o vidro tem de ser legível
# sobre qualquer coisa atrás — o pior caso é fundo branco OU preto.
FUNDOS_DESCONHECIDOS = [(255, 255, 255), (0, 0, 0), (128, 128, 128)]
