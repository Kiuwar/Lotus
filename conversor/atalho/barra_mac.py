"""Ícone do Lotus na barra de menus do Mac (o equivalente ao ícone ao lado do
relógio do Windows, bandeja.py).

Pelo menu dá para converter os arquivos selecionados no Finder SEM a
permissão de Acessibilidade (só a de Automação do Finder, para saber quais
arquivos estão selecionados). Regra 14 (por analogia): o clique no menu só
enfileira um texto em `comandos`; quem executa é o agente, na thread principal.

API do AppKit (pyobjc): NSStatusBar.systemStatusBar().statusItemWithLength_,
NSMenu/NSMenuItem com alvo e ação. Os nomes usados estão em NOMES_BARRA e o
CI do Mac confere que existem e que o menu dispara a ação.
"""

from __future__ import annotations

import queue
from functools import lru_cache

CONVERTER, ABRIR, ATALHO, ATIVAR, AJUDA, SAIR = (
    "converter", "abrir", "atalho", "ativar", "ajuda", "sair")

NOMES_BARRA = ["NSStatusBar", "NSVariableStatusItemLength", "NSMenu", "NSMenuItem", "NSImage",
               "NSControlStateValueOn", "NSControlStateValueOff"]


def itens_menu(atalho_ativo: bool, atalho_desc: str) -> list[tuple[str | None, str, bool]]:
    """(comando, texto, marcado); comando None = separador."""
    return [
        (CONVERTER, "Converter os arquivos selecionados no Finder…", False),
        (ABRIR, "Abrir o Lotus", False),
        (None, "", False),
        (ATALHO, f"Painel por atalho ({atalho_desc})", atalho_ativo),
        (ATIVAR, "Ativar o painel no Mac…", False),
        (AJUDA, "Ajuda", False),
        (None, "", False),
        (SAIR, "Tirar o Lotus da barra de menus", False),
    ]


@lru_cache(maxsize=1)
def _classe_alvo():
    """Classe Objective-C criada uma vez por processo (nomes não podem repetir)."""
    import objc
    from Foundation import NSObject

    class LotusAlvoBarra(NSObject):
        def initComFila_(self, fila):
            self = objc.super(LotusAlvoBarra, self).init()
            if self is None:
                return None
            self.fila = fila
            return self

        def acionar_(self, item):
            self.fila.put(str(item.representedObject()))

    return LotusAlvoBarra


class BarraMac:
    """Cria o ícone e o menu. Só na thread principal (a do Tk no agente)."""

    def __init__(self, comandos: queue.Queue, icone: str, atalho_ativo: bool, atalho_desc: str):
        from AppKit import NSImage, NSMenu, NSStatusBar, NSVariableStatusItemLength

        self.comandos = comandos
        self.alvo = _classe_alvo().alloc().initComFila_(comandos)
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        imagem = NSImage.alloc().initWithContentsOfFile_(icone)
        if imagem is not None:
            imagem.setSize_((18, 18))
            self.item.button().setImage_(imagem)
        else:
            self.item.button().setTitle_("Lotus")
        self.item.button().setToolTip_("Lotus — conversor de arquivos")
        self.menu = NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.item.setMenu_(self.menu)
        self._itens = {}
        self.atualizar(atalho_ativo, atalho_desc)

    def atualizar(self, atalho_ativo: bool, atalho_desc: str) -> None:
        from AppKit import NSControlStateValueOff, NSControlStateValueOn, NSMenuItem

        self.menu.removeAllItems()
        self._itens.clear()
        for cmd, texto, marcado in itens_menu(atalho_ativo, atalho_desc):
            if cmd is None:
                self.menu.addItem_(NSMenuItem.separatorItem())
                continue
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(texto, "acionar:", "")
            mi.setTarget_(self.alvo)
            mi.setRepresentedObject_(cmd)
            mi.setState_(NSControlStateValueOn if marcado else NSControlStateValueOff)
            self.menu.addItem_(mi)
            self._itens[cmd] = mi

    def remover(self) -> None:
        from AppKit import NSStatusBar

        if self.item is not None:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
            self.item = None
