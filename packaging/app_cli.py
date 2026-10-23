"""Ponto de entrada do executável de linha de comando (PyInstaller --console)."""

import sys

from conversor.cli import main

sys.exit(main())
