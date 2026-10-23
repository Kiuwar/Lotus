"""Ponto de entrada do Lotus.exe (PyInstaller --windowed)."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    # Rodando do código-fonte (ex.: menu instalado em modo desenvolvimento).
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversor.launcher import main  # noqa: E402

sys.exit(main())
