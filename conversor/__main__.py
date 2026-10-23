"""Sem argumentos abre a interface gráfica; com argumentos, usa a CLI."""

import sys


def run() -> int:
    if len(sys.argv) > 1:
        from conversor.cli import main

        return main()
    from conversor.gui import main

    return main()


if __name__ == "__main__":
    sys.exit(run())
