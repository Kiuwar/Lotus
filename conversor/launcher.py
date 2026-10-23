"""Ponto de entrada do Lotus.exe: decide o que abrir conforme os argumentos.

    Lotus.exe                          janela principal
    Lotus.exe a.png b.jpg              janela principal com os arquivos
    Lotus.exe --menu-converter pdf a   conversão direta (menu do botão direito)
    Lotus.exe --menu-escolher a        janela de escolha de formato
    Lotus.exe --instalar-menu          instala o menu do botão direito
    Lotus.exe --remover-menu           remove o menu
    Lotus.exe --reparar                diagnostica e repara

Nenhum erro é engolido: falhas inesperadas vão para o log e aparecem numa
caixa de mensagem (o .exe com janela não tem console para mostrar erros).
"""

from __future__ import annotations

import sys

from conversor.logs import get_logger, log_file

TITLE = "Lotus"


def _show(text: str, error: bool = False) -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    (messagebox.showerror if error else messagebox.showinfo)(TITLE, text, parent=root)
    root.destroy()


def _auto_repair_menu() -> None:
    """Se o menu está instalado mas desatualizado (ex.: .exe movido), corrige em silêncio."""
    if sys.platform != "win32":
        return
    try:
        from conversor import diagnostics

        installed, problems = diagnostics.menu_state()
        if installed and problems:
            diagnostics.repair_menu()
            get_logger().info("menu reparado automaticamente (%d problemas)", len(problems))
    except Exception:
        get_logger().exception("falha no reparo automático do menu")


def dispatch(argv: list[str]) -> int:
    if argv and argv[0].startswith("--menu-"):
        from conversor.gui import _enable_dpi_awareness

        _enable_dpi_awareness()

    if argv and argv[0] == "--menu-converter":
        if len(argv) < 3:
            _show("Uso: --menu-converter FORMATO ARQUIVO…", error=True)
            return 2
        from conversor.menu import quick_convert

        return quick_convert(argv[2:], argv[1])

    if argv and argv[0] == "--menu-escolher":
        from conversor.menu import choose

        return choose(argv[1:])

    if argv and argv[0] == "--instalar-menu":
        from conversor import shell

        n = shell.install()
        _show(f"Menu \"Converter para\" instalado em {n} tipos de arquivo.\n"
              "No Windows 11, ele aparece em \"Mostrar mais opções\".")
        return 0

    if argv and argv[0] == "--remover-menu":
        from conversor import shell

        n = shell.uninstall()
        _show(f"Menu removido de {n} tipos de arquivo.")
        return 0

    if argv and argv[0] == "--reparar":
        from conversor import diagnostics

        _show("\n".join(diagnostics.run()))
        return 0

    _auto_repair_menu()
    from conversor.gui import main as gui_main

    return gui_main(argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return dispatch(argv)
    except Exception as e:
        get_logger().exception("erro inesperado: %r", argv)
        try:
            _show(f"Erro inesperado: {e}\n\nDetalhes: {log_file()}", error=True)
        except Exception:
            pass
        return 1
