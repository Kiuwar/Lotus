"""Validação da saída: reabre o arquivo gerado com um leitor independente.

Retorna None se estiver ok, ou uma string descrevendo o problema.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

from conversor.core.detect import sniff

IMAGE_FORMATS = {"png", "jpg", "webp", "bmp", "gif", "tiff", "ico", "avif"}
MEDIA_FORMATS = {"mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "aiff",
                 "mp4", "mkv", "webm", "avi", "mov", "wmv", "mpeg", "m4v"}


def check(path: Path, fmt: str) -> str | None:
    if not path.is_file() or path.stat().st_size == 0:
        return "arquivo não foi gerado ou está vazio"

    if fmt in IMAGE_FORMATS:
        from PIL import Image

        try:
            with Image.open(path) as im:
                im.verify()
        except Exception as e:
            return f"imagem ilegível: {e}"
        real = sniff(path)
        if real != fmt:
            return f"assinatura esperada {fmt}, encontrada {real}"
        return None

    if fmt == "pdf":
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            return "cabeçalho %PDF- ausente"
        if b"%%EOF" not in data[-1024:]:
            return "marcador %%EOF ausente (PDF truncado)"
        return None

    if fmt == "json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"JSON inválido: {e}"
        return None

    if fmt == "csv":
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter=_csv_delim(path)))
        except Exception as e:
            return f"CSV ilegível: {e}"
        return None if rows else "CSV sem linhas"

    if fmt == "xlsx":
        from openpyxl import load_workbook

        try:
            load_workbook(path, read_only=True).close()
        except Exception as e:
            return f"XLSX ilegível: {e}"
        return None

    if fmt in {"pptx", "odt", "odp", "xps", "rtf"}:
        real = sniff(path)
        return None if real == fmt else f"não é um {fmt.upper()} válido (conteúdo: {real})"

    if fmt in {"doc", "ppt"}:
        return None if sniff(path) == "ole2" else f"não é um {fmt.upper()} (Office 97–2003) válido"

    if fmt == "docx":
        # Um DOCX é um zip com word/document.xml; sniff() confere isso. Depois, as
        # partes XML precisam ser XML bem formado (senão o Word recusa abrir).
        if sniff(path) != "docx":
            return "não é um DOCX válido (falta word/document.xml)"
        return _check_docx_xml(path) or _docx_com_bytes_de_pdf(path)

    if fmt in {"html", "txt", "md"}:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            return f"texto não está em UTF-8: {e}"
        return None

    if fmt in MEDIA_FORMATS:
        return _check_media(path)

    if fmt in MODELOS_3D:
        return _check_malha(path, fmt)

    if fmt == "svg":
        from defusedxml import ElementTree as ET

        try:
            raiz = ET.parse(str(path)).getroot()
        except Exception as e:
            return f"SVG com XML inválido: {e}"
        return None if raiz.tag.endswith("svg") else "não é um SVG (falta <svg>)"

    if fmt == "dxf":
        import ezdxf

        try:
            doc = ezdxf.readfile(str(path))
        except Exception as e:
            return f"DXF ilegível: {e}"
        return None if len(doc.modelspace()) else "DXF sem nenhum desenho"

    return f"sem validador para {fmt}: adicione um em validate.py"


def _check_docx_xml(path: Path) -> str | None:
    import zipfile

    from defusedxml import ElementTree as ET

    try:
        with zipfile.ZipFile(path) as z:
            nomes = set(z.namelist())
            if "[Content_Types].xml" not in nomes:
                return "DOCX sem [Content_Types].xml"
            for nome in sorted(n for n in nomes if n.endswith((".xml", ".rels"))):
                ET.fromstring(z.read(nome))
            corpo = ET.fromstring(z.read("word/document.xml")).find(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body")
    except Exception as e:
        return f"DOCX com XML inválido: {e}"
    return None if corpo is not None else "DOCX sem corpo (w:body)"


def docx_texto(path: Path, limite: int = 200_000) -> str:
    """Texto visível do DOCX (só w:t), para conferir o conteúdo."""
    import re
    import zipfile

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")[: limite * 4].decode("utf-8", "replace")
    pedacos = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml)
    return " ".join(pedacos)[:limite]


def _docx_com_bytes_de_pdf(path: Path) -> str | None:
    """Relato real (0.11.0): o Word abriu um PDF como TEXTO e salvou o código do
    PDF ("%PDF-1.4 … obj … endobj") dentro do DOCX. Isso não é um documento."""
    texto = docx_texto(path, 20_000)
    marcas = texto.count(" obj") + texto.count("endobj") + texto.count("endstream")
    if "%PDF-" in texto[:300] or marcas >= 20:
        return "o DOCX contém o código interno de um PDF em vez do texto"
    return None


MODELOS_3D = {"stl", "obj", "3mf", "ply", "off", "glb"}


def _check_malha(path: Path, fmt: str) -> str | None:
    import trimesh

    try:
        malha = trimesh.load(str(path), file_type=fmt, force="mesh", allow_remote=False)
    except Exception as e:
        return f"{fmt.upper()} ilegível: {e}"
    if len(getattr(malha, "faces", [])) == 0:
        return f"{fmt.upper()} sem triângulos"
    return None


def _csv_delim(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as f:
        first = f.readline()
    return ";" if first.count(";") > first.count(",") else ","


def _check_media(path: Path) -> str | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None  # sem ffprobe só dá para checar que não está vazio (feito acima)
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        **_no_window(),
    )
    if proc.returncode != 0:
        return f"ffprobe rejeitou o arquivo: {proc.stderr.strip()[:200]}"
    return None


def _no_window() -> dict:
    """No Windows, evita abrir uma janela de console a cada chamada ao ffmpeg."""
    import sys

    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
