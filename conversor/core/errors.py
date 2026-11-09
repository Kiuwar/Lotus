"""Traduz exceções técnicas em mensagens com "como resolver".

Regra: só sugerir ações que o usuário pode realmente fazer. Para erros não
mapeados, mostrar a mensagem original e apontar o log, sem adivinhar a causa.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path


def _mesmo(a, b: Path) -> bool | None:
    """True/False se `a` e `b` são o mesmo caminho; None se não dá para saber."""
    try:
        return os.path.normcase(os.path.abspath(str(a)).replace("\\\\?\\", "")) == \
            os.path.normcase(os.path.abspath(str(b)).replace("\\\\?\\", ""))
    except (OSError, ValueError):
        return None


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
        alvo = getattr(exc, "filename", None)
        if src is not None and alvo and _mesmo(alvo, src) is False:
            longo = len(str(alvo)) >= 240
            return (
                f"Não foi possível gravar a saída de {name}"
                + (" porque o caminho da pasta é longo demais para o Windows" if longo else "")
                + ". Como resolver: escolha uma pasta de saída mais curta (ex.: C:\\Convertidos) "
                "ou mova o arquivo para uma pasta com nome menor."
            )
        if src is not None and src.exists():
            return (
                f"O Windows não conseguiu abrir {name}, embora ele exista. Como resolver: se ele "
                "está no OneDrive, clique com o botão direito → \"Sempre manter neste dispositivo\"; "
                "ou mova o arquivo para uma pasta com caminho mais curto e tente de novo."
            )
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
