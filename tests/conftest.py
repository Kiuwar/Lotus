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
import sys
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


_DIALOGOS = {
    "messagebox": [("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"),
                   ("askyesno", False), ("askokcancel", False), ("askyesnocancel", None),
                   ("askquestion", "no"), ("askretrycancel", False)],
    "colorchooser": [("askcolor", (None, None))],
    "filedialog": [("askopenfilenames", ""), ("askopenfilename", ""), ("askdirectory", ""),
                   ("asksaveasfilename", "")],
}


@pytest.fixture(autouse=True)
def _sem_dialogos_reais(monkeypatch):
    """Uma caixa de diálogo real trava o teste até alguém clicar (no Mac é um
    alerta nativo modal: o CI ficou parado 14 min). Aqui o diálogo só é
    registrado no stderr do teste. Testes que conferem um diálogo fazem o
    próprio monkeypatch por cima deste."""
    try:
        import importlib

        modulos = {n: importlib.import_module(f"tkinter.{n}") for n in _DIALOGOS}
    except ImportError:
        return

    def falso(nome, resposta):
        def f(*args, **kwargs):
            print(f"[diálogo {nome}] {args} {kwargs.get('message', '')}", file=sys.stderr)
            return resposta
        return f

    for mod, funcs in _DIALOGOS.items():
        for nome, resposta in funcs:
            monkeypatch.setattr(modulos[mod], nome, falso(nome, resposta))


# ---------- erros do Tcl em segundo plano ----------
# Erro num script Tcl de evento (after, binding) chama o comando `bgerror`;
# o padrão do Tk (bgerror.tcl, carregado sob demanda) abre um diálogo com
# grab + vwait que trava o teste dentro do update() — no Mac isso apareceu
# como travamento sem nenhuma linha Python na pilha. Aqui o `bgerror` é
# nosso: registra a mensagem e a pilha Tcl, e o teste falha mostrando-as.
ERROS_TCL: list[str] = []

try:
    import tkinter as _tk
except ImportError:  # pragma: no cover
    _tk = None

if _tk is not None:
    _tk_init_original = _tk.Tk.__init__

    def _tk_init_com_bgerror(self, *args, **kwargs):
        _tk_init_original(self, *args, **kwargs)

        def bgerror(msg):
            try:
                pilha = self.tk.globalgetvar("errorInfo")
            except _tk.TclError:
                pilha = ""
            ERROS_TCL.append(f"{msg}\n{pilha}")
            print(f"[bgerror do Tk] {msg}\n{pilha}", file=sys.stderr)

        self.tk.createcommand("bgerror", bgerror)

    _tk.Tk.__init__ = _tk_init_com_bgerror


@pytest.fixture(autouse=True)
def _sem_erros_tcl():
    ERROS_TCL.clear()
    yield
    erros, ERROS_TCL[:] = list(ERROS_TCL), []
    assert not erros, "erro do Tcl em segundo plano:\n" + "\n---\n".join(erros)
