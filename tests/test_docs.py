import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_formatos_md_is_up_to_date():
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "gerar_formatos.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    current = (ROOT / "docs" / "FORMATOS.md").read_text(encoding="utf-8")
    assert current == gen.render(), "Rode: python scripts/gerar_formatos.py"
