"""Gera conversor/recursos/lotus.ico, lotus.icns e lotus.png (ícone do Lotus).

Rode após mudar o desenho em conversor/ui/icone.py; o teste
tests/test_icone.py falha se os arquivos estiverem desatualizados.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversor.ui import icone  # noqa: E402

if __name__ == "__main__":
    for tipo, caminho in icone.gerar().items():
        print(f"{tipo}: {caminho} ({caminho.stat().st_size} bytes)")
