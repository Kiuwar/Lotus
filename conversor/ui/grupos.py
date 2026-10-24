"""Separa os formatos de DESTINO em grupos (Imagem, Documento, …).

A lista de destinos vem do registro de conversões; este módulo só decide em
qual grupo cada formato aparece e com qual nome curto.
"""

from __future__ import annotations

from conversor.ui.tema import GRUPOS

FAMILIA = {
    "png": "Imagem", "jpg": "Imagem", "webp": "Imagem", "bmp": "Imagem",
    "gif": "Imagem", "tiff": "Imagem", "ico": "Imagem", "avif": "Imagem", "heic": "Imagem",
    "pdf": "Documento", "docx": "Documento", "html": "Documento", "doc": "Documento",
    "rtf": "Documento", "odt": "Documento", "xps": "Documento",
    "pptx": "Documento", "ppt": "Documento", "odp": "Documento",
    "txt": "Texto e dados", "md": "Texto e dados", "csv": "Texto e dados",
    "json": "Texto e dados", "xlsx": "Texto e dados",
    "mp3": "Áudio", "wav": "Áudio", "ogg": "Áudio", "flac": "Áudio", "m4a": "Áudio",
    "aac": "Áudio", "opus": "Áudio", "wma": "Áudio", "aiff": "Áudio",
    "mp4": "Vídeo", "mkv": "Vídeo", "webm": "Vídeo", "avi": "Vídeo", "mov": "Vídeo",
    "wmv": "Vídeo", "mpeg": "Vídeo", "m4v": "Vídeo",
}

ROTULO = {"docx": "Word", "xlsx": "Excel", "md": "MD"}

# Ordem dentro do grupo: os mais usados primeiro.
_PRIORIDADE = ["pdf", "docx", "png", "jpg", "txt", "xlsx", "csv", "mp3", "mp4"]


def rotulo(fmt: str) -> str:
    return ROTULO.get(fmt, fmt.upper())


def agrupar(destinos: list[str]) -> list[tuple[str, list[str]]]:
    """[(grupo, [formatos])] na ordem de GRUPOS, sem grupos vazios."""
    por_grupo: dict[str, list[str]] = {g: [] for g in GRUPOS}
    for fmt in destinos:
        por_grupo[FAMILIA.get(fmt, "Texto e dados")].append(fmt)

    def chave(f: str) -> tuple[int, str]:
        return (_PRIORIDADE.index(f) if f in _PRIORIDADE else len(_PRIORIDADE), f)

    return [(g, sorted(fs, key=chave)) for g, fs in por_grupo.items() if fs]
