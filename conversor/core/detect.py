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
    "markdown": "md",
    "htm": "html",
}

TEXT_FORMATS = {"csv", "json", "txt", "md"}

_WEAK_SIGNATURES = {"bmp", "mp3"}

# Formatos que compartilham o mesmo contêiner: a assinatura não distingue com
# segurança, então aceitamos a extensão se ela estiver no mesmo grupo.
_FAMILIES = [
    {"mp4", "m4a", "mov"},
    {"mkv", "webm"},
]


class DetectionError(Exception):
    pass


@dataclass(frozen=True)
class Detection:
    fmt: str
    warning: str | None = None


def normalize_ext(name_or_ext: str) -> str:
    ext = name_or_ext.rsplit(".", 1)[-1].lower() if "." in name_or_ext else name_or_ext.lower()
    return ALIASES.get(ext, ext)


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
        return "ogg"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand.startswith(b"M4A"):
            return "m4a"
        if brand == b"qt  ":
            return "mov"
        return "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm" if b"webm" in head else "mkv"
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "word/document.xml" in names:
            return "docx"
        return "zip"
    return None


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

    if magic == ext or _same_family(magic, ext):
        return Detection(ext)

    return Detection(
        magic,
        warning=(
            f"{path.name}: a extensão diz .{ext}, mas o conteúdo é {magic.upper()}. "
            f"Usando {magic.upper()}."
        ),
    )
