"""Reúne num só pedido os arquivos de uma seleção múltipla do Explorer.

Com vários arquivos selecionados, o Explorer abre UM Lotus.exe por arquivo
("%1"). Para "Juntar em um PDF" precisamos de todos juntos: cada processo
anota o seu arquivo numa fila em disco; o primeiro (dono) espera a fila parar
de crescer e devolve a lista na ordem de chegada; os outros saem em silêncio.
Só arquivos locais na pasta do Lotus; nada de rede (regra 8).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

ESPERA_QUIETA = 0.8   # s sem novos arquivos = seleção completa
ESPERA_MAXIMA = 8.0   # s, teto de segurança
DONO_VELHO = 30.0     # s: trava esquecida por um processo que morreu


def pasta_padrao() -> Path:
    from conversor.logs import log_dir

    return log_dir()


def _ler(fila: Path) -> list[str]:
    try:
        linhas = fila.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return list(dict.fromkeys(l for l in linhas if l.strip()))


def reunir(arquivo: str, nome: str = "juntar", pasta: Path | None = None,
           dormir=time.sleep, agora=time.monotonic) -> list[str] | None:
    """Devolve a lista completa no processo dono; None nos demais."""
    pasta = pasta or pasta_padrao()
    pasta.mkdir(parents=True, exist_ok=True)
    fila = pasta / f"{nome}.fila"
    dono = pasta / f"{nome}.dono"
    with open(fila, "a", encoding="utf-8") as f:
        f.write(str(Path(arquivo).resolve()) + "\n")
    try:
        if dono.exists() and time.time() - dono.stat().st_mtime > DONO_VELHO:
            dono.unlink()
        os.close(os.open(dono, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return None
    try:
        inicio = ultimo = agora()
        visto = len(_ler(fila))
        while agora() - ultimo < ESPERA_QUIETA and agora() - inicio < ESPERA_MAXIMA:
            dormir(0.1)
            n = len(_ler(fila))
            if n != visto:
                visto, ultimo = n, agora()
        arquivos = _ler(fila)
        fila.unlink(missing_ok=True)
        return arquivos
    finally:
        dono.unlink(missing_ok=True)
