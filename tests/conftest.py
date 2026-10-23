"""Gera arquivos de exemplo reais para cada formato de origem.

Nada de arquivos "falsos": cada amostra é produzida pela própria biblioteca
ou pelo ffmpeg, para que o teste exercite o caminho real de conversão.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import subprocess
from pathlib import Path

import pytest
from PIL import Image

# O log de erros dos testes vai para uma pasta temporária, não para a do usuário.
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="lotus-test-log-")
# Idem para a configuração do atalho (%APPDATA%\Lotus\config.json).
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="lotus-test-config-")

HAS_FFMPEG = shutil.which("ffmpeg") is not None

CSV_TEXT = 'nome;cep;preço\nJoão;01234-000;10,50\nAna;"=SOMA(1;2)";7\n'
JSON_DATA = [
    {"nome": "João", "cep": "01234-000", "itens": [1, 2]},
    {"nome": "Ana", "idade": 30},
]


def make_sample(fmt: str, folder: Path) -> Path:
    path = folder / f"amostra.{fmt}"
    if fmt in {"png", "webp", "gif", "tiff", "ico"}:
        im = Image.new("RGBA", (64, 48), (255, 0, 0, 128))
        im.save(path)
    elif fmt in {"jpg", "bmp"}:
        Image.new("RGB", (64, 48), (0, 128, 255)).save(path)
    elif fmt == "csv":
        path.write_text(CSV_TEXT, encoding="utf-8")
    elif fmt == "json":
        path.write_text(json.dumps(JSON_DATA, ensure_ascii=False), encoding="utf-8")
    elif fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["nome", "valor"])
        ws.append(["Café", 3.5])
        wb.save(path)
    elif fmt == "txt":
        path.write_text("Olá, ação e coração.\n\tLinha com tab.\n" + "x" * 300, encoding="utf-8")
    elif fmt == "md":
        path.write_text("# Título\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    elif fmt == "pdf":
        make_pdf(path, ["Página 1: ação e coração", "Página 2: São Paulo"])
    elif fmt == "docx":
        make_docx(path, "Petição: ação de cobrança")
    elif fmt in {"mp3", "wav", "ogg", "flac", "m4a"}:
        _ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1"], path)
    elif fmt in {"mp4", "mkv", "webm", "avi", "mov"}:
        _ffmpeg(
            [
                "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-pix_fmt", "yuv420p", "-shortest",
            ],
            path,
        )
    else:
        raise ValueError(f"sem gerador de amostra para {fmt}: adicione em conftest.py")
    return path


def make_pdf(path: Path, paginas: list[str]) -> Path:
    """PDF real com texto (fonte Unicode quando houver, para os acentos)."""
    from fpdf import FPDF

    from conversor.converters.documents import _FONT_CANDIDATES

    pdf = FPDF(format="A4")
    fonte = next((f for f in _FONT_CANDIDATES if f.is_file()), None)
    if fonte:
        pdf.add_font("T", fname=str(fonte))
    for texto in paginas:
        pdf.add_page()
        pdf.set_font("T" if fonte else "Helvetica", size=14)
        pdf.cell(0, 10, texto)
    pdf.output(str(path))
    return path


def make_docx(path: Path, texto: str) -> Path:
    """DOCX mínimo válido (3 partes obrigatórias do formato), sem depender do Word."""
    import zipfile
    from xml.sax.saxutils import escape

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'))
        z.writestr("word/document.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{escape(texto)}</w:t></w:r></w:p></w:body></w:document>'))
    return path


def _ffmpeg(args: list[str], out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *args, str(out)],
        check=True,
    )


@pytest.fixture
def sample(tmp_path):
    def _make(fmt: str) -> Path:
        d = tmp_path / f"src_{fmt}"
        d.mkdir(exist_ok=True)
        return make_sample(fmt, d)

    return _make
