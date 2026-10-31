"""Detecção do formato real de um arquivo.

A extensão do nome do arquivo pode mentir (ex.: "foto.png" que na verdade é
JPEG). Para formatos binários, o conteúdo (assinatura / "magic bytes") manda.
Para formatos de texto (csv, json, txt, md) não há assinatura confiável, então
usamos a extensão e confirmamos apenas que o conteúdo é texto.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

ALIASES = {
    "jpeg": "jpg",
    "jpe": "jpg",
    "tif": "tiff",
    "heif": "heic",
    "hif": "heic",
    "markdown": "md",
    "htm": "html",
    "aif": "aiff",
    "mpg": "mpeg",
}

TEXT_FORMATS = {"csv", "json", "txt", "md", "html", "obj", "svg", "dxf"}

_WEAK_SIGNATURES = {"bmp", "mp3", "aac"}

# Formatos que compartilham o mesmo contêiner: a assinatura não distingue com
# segurança, então aceitamos a extensão se ela estiver no mesmo grupo.
_FAMILIES = [
    {"mp4", "m4a", "mov", "m4v"},
    {"mkv", "webm"},
    {"ogg", "opus"},
    {"wma", "wmv"},  # ASF: o mesmo cabeçalho para áudio e vídeo
]


OLE2 = bytes.fromhex("d0cf11e0a1b11ae1")  # Compound File (Office 97–2003)
OFFICE_ANTIGO = {"doc", "ppt", "xls"}


class DetectionError(Exception):
    pass


@dataclass(frozen=True)
class Detection:
    fmt: str
    warning: str | None = None


def normalize_ext(name_or_ext: str) -> str:
    ext = name_or_ext.rsplit(".", 1)[-1].lower() if "." in name_or_ext else name_or_ext.lower()
    return ALIASES.get(ext, ext)


# Marcas ISO-BMFF das imagens HEIF (ISO/IEC 23008-12) e AVIF (AV1 Image File
# Format). "mif1"/"msf1" são genéricas: aí as marcas compatíveis decidem.
_MARCAS_AVIF = {b"avif", b"avis"}
_MARCAS_HEIC = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx"}
_MARCAS_HEIF_GENERICAS = {b"mif1", b"msf1"}


def _marca_heif(head: bytes) -> str | None:
    principal = head[8:12]
    tamanho = int.from_bytes(head[0:4], "big")
    compativeis = {head[i:i + 4] for i in range(16, min(tamanho, len(head)) - 3, 4)}
    if principal in _MARCAS_AVIF:
        return "avif"
    if principal in _MARCAS_HEIC:
        return "heic"
    if principal in _MARCAS_HEIF_GENERICAS:
        if compativeis & _MARCAS_AVIF:
            return "avif"
        if compativeis & _MARCAS_HEIC:
            return "heic"
    return None


def sniff(path: Path) -> str | None:
    """Retorna o formato pela assinatura binária, ou None se não reconhecido."""
    with open(path, "rb") as f:
        head = f.read(64)

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head.startswith(b"BM"):
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:4] == b"\x00\x00\x01\x00":
        return "ico"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head[:4] == b"glTF":
        return "glb"  # glTF binário
    if head[:4] in (b"ply\n", b"ply\r"):
        return "ply"
    if head[:3] == b"OFF" or head[:4] == b"COFF":
        return "off"
    if head[:4] == b"RIFF":
        kind = head[8:12]
        if kind == b"WEBP":
            return "webp"
        if kind == b"WAVE":
            return "wav"
        if kind == b"AVI ":
            return "avi"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"OggS"):
        return "opus" if head[28:36] == b"OpusHead" else "ogg"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if head[0:1] == b"\xff" and len(head) > 1 and head[1] & 0xF6 == 0xF0:
        return "aac"  # ADTS: sincronismo 0xFFF, camada 00
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if head[:16] == bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"):
        return "wmv"  # ASF (WMA/WMV); a extensão decide entre os dois
    if head[:4] == b"\x00\x00\x01\xba":
        return "mpeg"  # MPEG program stream
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        imagem = _marca_heif(head)
        if imagem:
            return imagem
        if brand.startswith(b"M4A"):
            return "m4a"
        if brand == b"M4V ":
            return "m4v"
        if brand == b"qt  ":
            return "mov"
        return "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm" if b"webm" in head else "mkv"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if head[:8] == OLE2:
        return "ole2"  # .doc/.ppt/.xls antigos: o contêiner é o mesmo; a extensão decide
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                mime = z.read("mimetype")[:100] if "mimetype" in names else b""
        except (zipfile.BadZipFile, KeyError, OSError):
            return None
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "word/document.xml" in names:
            return "docx"
        if "ppt/presentation.xml" in names:
            return "pptx"
        if mime == b"application/vnd.oasis.opendocument.text":
            return "odt"
        if mime == b"application/vnd.oasis.opendocument.presentation":
            return "odp"
        if any(n.lower() == "3d/3dmodel.model" for n in names):
            return "3mf"  # pacote 3MF (impressão 3D)
        if any(n.lower().endswith(".fdseq") for n in names):
            return "xps"  # pacote XPS: tem uma sequência de documentos fixos
        return "zip"
    return None


def _parece_stl(path: Path) -> bool:
    """STL binário: 80 bytes de cabeçalho + nº de triângulos + 50 bytes cada.
    STL texto: começa com "solid" e tem "facet"."""
    tamanho = path.stat().st_size
    with open(path, "rb") as f:
        inicio = f.read(1024)
    if tamanho >= 84 and 84 + 50 * int.from_bytes(inicio[80:84], "little") == tamanho:
        return True
    return inicio.lstrip().lower().startswith(b"solid") and b"facet" in inicio.lower()


def _looks_like_text(path: Path) -> bool:
    with open(path, "rb") as f:
        chunk = f.read(8192)
    return b"\x00" not in chunk


def _same_family(a: str, b: str) -> bool:
    return any(a in fam and b in fam for fam in _FAMILIES)


def detect(path: Path) -> Detection:
    path = Path(path)
    if not path.is_file():
        raise DetectionError(f"Arquivo não encontrado: {path}")
    if path.stat().st_size == 0:
        raise DetectionError(f"Arquivo vazio: {path.name}")

    ext = normalize_ext(path.name)
    if ext == "stl":  # STL binário não tem assinatura: confere tamanho ou texto
        if _parece_stl(path):
            return Detection("stl")
        raise DetectionError(f"{path.name}: extensão .stl, mas o conteúdo não é um STL válido.")
    magic = sniff(path)

    # "BM" (BMP) e 0xFFFB (MP3) são assinaturas curtas que um texto pode
    # começar por acaso (ex.: CSV com cabeçalho "BMW;..."). Nesses casos,
    # se a extensão é de texto e o conteúdo é texto, vale a extensão.
    if magic in _WEAK_SIGNATURES and ext in TEXT_FORMATS and _looks_like_text(path):
        magic = None

    if magic is None:
        if ext in TEXT_FORMATS:
            if not _looks_like_text(path):
                raise DetectionError(
                    f"{path.name}: extensão .{ext} mas o conteúdo não é texto."
                )
            return Detection(ext)
        raise DetectionError(f"{path.name}: formato não reconhecido.")

    if magic == "ole2":
        if ext in OFFICE_ANTIGO:
            return Detection(ext)
        raise DetectionError(
            f"{path.name}: é um arquivo do Office antigo (Word .doc, PowerPoint .ppt ou Excel .xls), "
            "mas a extensão não diz qual. Como resolver: renomeie com a extensão certa."
        )

    if magic == ext or _same_family(magic, ext):
        return Detection(ext)

    return Detection(
        magic,
        warning=(
            f"{path.name}: a extensão diz .{ext}, mas o conteúdo é {magic.upper()}. "
            f"Usando {magic.upper()}."
        ),
    )
