"""Log de erros LOCAL, para diagnóstico. Nunca é enviado a lugar nenhum.

Fica em %LOCALAPPDATA%\\Lotus\\lotus.log (no Linux/macOS: ~/.lotus/lotus.log),
limitado a 3 arquivos de 512 KB. Contém nomes/caminhos de arquivos: o usuário
pode apagá-lo a qualquer momento.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_logger: logging.Logger | None = None


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Lotus" if base else Path.home() / ".lotus"


def log_file() -> Path:
    return log_dir() / "lotus.log"


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("lotus")
    logger.setLevel(logging.INFO)
    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_file(), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()  # sem permissão de escrita: segue sem log
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _logger = logger
    return logger
