"""Toda conversão registrada é executada de verdade e a saída é validada.

Se alguém registrar uma conversão nova sem amostra/validador, este teste
falha. É o que impede o app (ou a documentação) de prometer algo que não faz.
"""

from __future__ import annotations

import pytest

from conversor.core import registry
from conversor.core.engine import convert_file

from .conftest import HAS_FFMPEG

CASES = [(c.source, c.target, c.category) for c in registry.all_converters()]


@pytest.mark.parametrize("source,target,category", CASES, ids=[f"{s}->{t}" for s, t, _ in CASES])
def test_every_registered_conversion(source, target, category, sample, tmp_path):
    if category in ("Áudio", "Vídeo") and not HAS_FFMPEG:
        pytest.skip("ffmpeg não instalado")
    if not registry.find(source, target).available():
        pytest.skip(f"componente ausente: {registry.find(source, target).notes}")
    src = sample(source)
    before = src.read_bytes()

    result = convert_file(src, target, out_dir=tmp_path / "out")

    saidas = sorted(result.output.iterdir()) if result.output.is_dir() else [result.output]
    assert saidas and all(p.is_file() and p.suffix == f".{target}" for p in saidas)
    assert src.read_bytes() == before, "o arquivo de origem não pode ser alterado"
    leftovers = [p for p in result.output.parent.iterdir() if ".tmp-" in p.name]
    assert not leftovers, f"temporários esquecidos: {leftovers}"


def test_matrix_is_not_empty():
    assert len(CASES) > 50
