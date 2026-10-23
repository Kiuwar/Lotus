"""Lê os arquivos selecionados numa janela do Explorer (somente Windows).

Usa o objeto COM "Shell.Application" (pywin32), a interface documentada do
Windows para isso. Cada aba de uma janela do Explorer do Windows 11 aparece
como um item separado com o mesmo HWND, por isso o resultado é por aba.
"""

from __future__ import annotations

import os

from conversor.logs import get_logger


def iniciar_com() -> None:
    import pythoncom

    pythoncom.CoInitialize()


def selecoes(hwnd: int) -> dict[int, list[str]]:
    """{índice da aba: caminhos selecionados} para as abas da janela `hwnd`."""
    import win32com.client

    shell = win32com.client.Dispatch("Shell.Application")
    janelas = shell.Windows()
    out: dict[int, list[str]] = {}
    for i in range(janelas.Count):
        try:
            jan = janelas.Item(i)
            if jan is None or int(jan.HWND) != int(hwnd):
                continue
            itens = jan.Document.SelectedItems()
            out[i] = [itens.Item(j).Path for j in range(itens.Count)]
        except Exception as e:  # janela fechando, ou não é pasta do sistema de arquivos
            get_logger().info("aba ignorada ao ler seleção: %r", e)
    return out


def apenas_arquivos(caminhos: list[str]) -> list[str]:
    """Descarta pastas e itens virtuais (ex.: "Este Computador", dentro de .zip)."""
    return [c for c in caminhos if os.path.isfile(c)]
