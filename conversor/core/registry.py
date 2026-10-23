"""Registro central de conversões.

Este registro é a ÚNICA fonte de verdade sobre o que o aplicativo converte.
A interface, a CLI e a documentação (docs/FORMATOS.md) são geradas a partir
dele. Se uma conversão não está registrada aqui com teste correspondente,
ela não existe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ConvertFn = Callable[[Path, Path, dict], None]


@dataclass(frozen=True)
class Converter:
    source: str
    target: str
    fn: ConvertFn
    category: str
    notes: str = ""
    # Função que diz se a dependência externa (ex.: ffmpeg) está presente.
    available: Callable[[], bool] = field(default=lambda: True)


_REGISTRY: dict[tuple[str, str], Converter] = {}


def register(
    sources: list[str],
    targets: list[str],
    category: str,
    notes: str = "",
    available: Callable[[], bool] | None = None,
) -> Callable[[ConvertFn], ConvertFn]:
    """Registra `fn` para todos os pares (origem, destino) com origem != destino."""

    def decorator(fn: ConvertFn) -> ConvertFn:
        for src in sources:
            for dst in targets:
                if src == dst:
                    continue
                key = (src, dst)
                if key in _REGISTRY:
                    raise RuntimeError(f"Conversão duplicada: {src} -> {dst}")
                _REGISTRY[key] = Converter(
                    source=src,
                    target=dst,
                    fn=fn,
                    category=category,
                    notes=notes,
                    available=available or (lambda: True),
                )
        return fn

    return decorator


def _load_all() -> None:
    # Importar os módulos executa os decoradores @register.
    from conversor.converters import data, documents, images, media  # noqa: F401


def all_converters() -> list[Converter]:
    _load_all()
    return sorted(_REGISTRY.values(), key=lambda c: (c.category, c.source, c.target))


def find(source: str, target: str) -> Converter | None:
    _load_all()
    return _REGISTRY.get((source, target))


def targets_for(source: str, only_available: bool = True) -> list[str]:
    return sorted(
        c.target
        for c in all_converters()
        if c.source == source and (not only_available or c.available())
    )
