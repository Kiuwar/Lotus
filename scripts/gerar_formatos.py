"""Gera docs/FORMATOS.md a partir do registro de conversões.

A documentação nunca é escrita à mão: assim ela não pode prometer uma
conversão que o código não faz. O teste tests/test_docs.py falha se o
arquivo estiver desatualizado.

Uso: python scripts/gerar_formatos.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conversor.core import registry  # noqa: E402

OUT = ROOT / "docs" / "FORMATOS.md"


def render() -> str:
    by_cat: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    notes: dict[str, set[str]] = defaultdict(set)
    for c in registry.all_converters():
        by_cat[c.category][c.source].append(c.target)
        if c.notes:
            notes[c.category].add(c.notes)

    total = sum(len(t) for cat in by_cat.values() for t in cat.values())
    lines = [
        "# Formatos suportados",
        "",
        "<!-- Arquivo GERADO por scripts/gerar_formatos.py. Não edite à mão. -->",
        "",
        f"Total: **{total} conversões**, todas cobertas por tests/test_matrix.py.",
        "",
    ]
    for cat in sorted(by_cat):
        lines += [f"## {cat}", "", "| Origem | Destinos |", "|---|---|"]
        for src in sorted(by_cat[cat]):
            dsts = ", ".join(t.upper() for t in sorted(by_cat[cat][src]))
            lines.append(f"| {src.upper()} | {dsts} |")
        for n in sorted(notes[cat]):
            lines += ["", f"Observação: {n}"]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"Gerado {OUT.relative_to(ROOT)}")
