"""Decide, para cada evento de mouse, se é o gesto do Lotus.

Lógica pura (sem Windows), chamada pelo gancho de mouse. Precisa ser rápida:
o Windows descarta ganchos que demoram a responder.

Regras:
- Eventos gerados por programas (injetados) passam direto. Isso evita que o
  próprio clique simulado pelo Lotus dispare o gesto de novo.
- O gesto só vale dentro de janelas do Explorer; em qualquer outro programa
  o clique segue normal.
- Quando o gesto acontece, o "apertar" e o "soltar" desse botão são
  engolidos, para o Explorer não mudar a seleção nem abrir menus.
"""

from __future__ import annotations

from dataclasses import dataclass

from conversor.atalho.config import Gatilho

# Classes de janela do Explorer (pastas). A área de trabalho ("Progman" /
# "WorkerW") não é suportada: ver docs/ANALISE.md.
CLASSES_EXPLORER = {"CabinetWClass", "ExploreWClass"}

PASSAR = "passar"
ENGOLIR = "engolir"
DISPARAR = "disparar"


@dataclass
class Detector:
    gatilho: Gatilho
    _pendente: str | None = None  # botão cujo "soltar" deve ser engolido

    def evento(
        self,
        botao: str,
        apertou: bool,
        modificadores: set[str],
        injetado: bool,
        classe_janela: str,
    ) -> str:
        if injetado:
            return PASSAR
        if not apertou:
            if self._pendente == botao:
                self._pendente = None
                return ENGOLIR
            return PASSAR
        g = self.gatilho
        if (
            g.tipo == "mouse"
            and botao == g.botao
            and set(modificadores) == set(g.modificadores)  # exatamente essas teclas
            and classe_janela in CLASSES_EXPLORER
        ):
            self._pendente = botao
            return DISPARAR
        return PASSAR


def escolher_aba(antes: dict[int, list[str]], depois: dict[int, list[str]]) -> list[str]:
    """Com várias abas na mesma janela, acha a aba onde o clique simulado caiu.

    `antes`/`depois` mapeiam um índice de aba para os caminhos selecionados.
    A aba certa é a que mudou de seleção. Se nenhuma mudou (ex.: o arquivo já
    era o único selecionado), usa a única aba com seleção, se houver só uma.
    """
    mudou = [i for i in depois if depois[i] != antes.get(i)]
    if len(mudou) == 1:
        return depois[mudou[0]]
    com_selecao = [i for i in depois if depois[i]]
    if len(com_selecao) == 1:
        return depois[com_selecao[0]]
    return []
