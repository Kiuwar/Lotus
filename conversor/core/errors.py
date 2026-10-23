"""Traduz exceções técnicas em mensagens com "como resolver".

Regra: só sugerir ações que o usuário pode realmente fazer. Para erros não
mapeados, mostrar a mensagem original e apontar o log, sem adivinhar a causa.
"""

from __future__ import annotations

import errno
from pathlib import Path


def explain(exc: BaseException, src: Path | None = None) -> str:
    name = src.name if src else "o arquivo"

    if isinstance(exc, PermissionError):
        target = Path(exc.filename).name if getattr(exc, "filename", None) else name
        return (
            f"Sem permissão para acessar {target}. "
            "Como resolver: feche o arquivo no programa que o está usando (ex.: Excel, "
            "visualizador de fotos) ou escolha outra pasta de saída."
        )
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "Disco cheio. Como resolver: libere espaço ou escolha outra pasta de saída."
    if isinstance(exc, FileNotFoundError):
        return f"{name} não foi encontrado (foi movido ou apagado?)."
    if isinstance(exc, MemoryError):
        return (
            f"Memória insuficiente para converter {name}. "
            "Como resolver: feche outros programas ou converta arquivos menores."
        )
    if isinstance(exc, UnicodeDecodeError):
        return f"{name} tem caracteres que não puderam ser lidos ({exc.reason})."
    msg = str(exc) or exc.__class__.__name__
    return f"Falha ao converter {name}: {msg}. Detalhes técnicos foram gravados no log."
