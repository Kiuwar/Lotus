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


# IShellWindows::FindWindowSW (learn.microsoft.com, exdisp.h)
SWC_DESKTOP = 0x8
SWFO_NEEDDISPATCH = 0x1
CLSID_SHELLWINDOWS = "{9BA05972-F6A8-11CF-A442-00A0C90A8F39}"


def _janela_da_mesa():
    """Objeto da área de trabalho no Shell (com .Document.SelectedItems())."""
    import win32com.client

    janelas = win32com.client.Dispatch(CLSID_SHELLWINDOWS)
    # pvarLoc = 0 (PIDL vazio = Mesa), pvarLocRoot vazio, phwnd é de saída.
    r = janelas.FindWindowSW(0, 0, SWC_DESKTOP, 0, SWFO_NEEDDISPATCH)
    # O pywin32 pode devolver só o objeto ou (objeto, hwnd): aceita os dois.
    candidatos = r if isinstance(r, tuple) else (r,)
    for c in candidatos:
        if c is not None and not isinstance(c, int):
            return c
    return None


def selecoes_mesa() -> dict[int, list[str]]:
    """Seleção da área de trabalho, no mesmo formato de `selecoes` ({0: [...]})."""
    mesa = _janela_da_mesa()
    if mesa is None:
        get_logger().warning("área de trabalho não encontrada pelo Shell (FindWindowSW)")
        return {}
    itens = mesa.Document.SelectedItems()
    return {0: [itens.Item(j).Path for j in range(itens.Count)]}


def apenas_arquivos(caminhos: list[str]) -> list[str]:
    """Descarta pastas e itens virtuais (ex.: "Este Computador", dentro de .zip)."""
    return [c for c in caminhos if os.path.isfile(c)]
