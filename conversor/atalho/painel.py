"""Painel flutuante: aparece junto do cursor com um botão por formato.

Reaproveita a janela de escolha do menu do botão direito (menu.Chooser),
só que sem moldura, sempre na frente e posicionada no cursor.
"""

from __future__ import annotations

import tkinter as tk

from conversor.menu import Chooser


def posicao_na_tela(x: int, y: int, larg: int, alt: int, tela_l: int, tela_a: int) -> tuple[int, int]:
    """Coloca o painel logo abaixo/à direita do cursor sem sair da tela."""
    px, py = x + 12, y + 12
    if px + larg > tela_l:
        px = max(0, x - larg - 12)
    if py + alt > tela_a:
        py = max(0, y - alt - 12)
    return px, py


def abrir_painel(root: tk.Tk, arquivos: list[str], x: int, y: int) -> tk.Toplevel:
    top = tk.Toplevel(root)
    top.overrideredirect(True)  # sem barra de título: "flutuante"
    top.attributes("-topmost", True)
    borda = tk.Frame(top, borderwidth=1, relief="solid")
    borda.pack(fill="both", expand=True)
    Chooser(borda, arquivos)
    top.update_idletasks()
    px, py = posicao_na_tela(
        x, y, top.winfo_reqwidth(), top.winfo_reqheight(),
        top.winfo_screenwidth(), top.winfo_screenheight(),
    )
    top.geometry(f"+{px}+{py}")
    top.bind("<Escape>", lambda _e: top.destroy())
    top.focus_force()
    return top
