"""Conversões de documentos de texto."""

from __future__ import annotations

import html
import os
from pathlib import Path

from conversor.core.registry import register

# Fontes TrueType com acentuação completa. A primeira encontrada é usada.
_FONT_CANDIDATES = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
]


def _read_text(src: Path, options: dict) -> str:
    raw = src.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        options.setdefault("_warnings", []).append(
            f"{src.name} não está em UTF-8; lido como Windows-1252."
        )
        return raw.decode("cp1252", errors="replace")


@register(["txt"], ["pdf"], category="Documento", notes="Texto simples, A4, fonte 11.")
def txt_to_pdf(src: Path, dst: Path, options: dict) -> None:
    from fpdf import FPDF

    text = _read_text(src, options).replace("\t", "    ").replace("\r\n", "\n")
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    font = next((p for p in _FONT_CANDIDATES if p.is_file()), None)
    if font:
        pdf.add_font("Texto", fname=str(font))
        pdf.set_font("Texto", size=11)
    else:
        # Fonte embutida do PDF só cobre Latin-1: caracteres fora dela viram "?".
        pdf.set_font("Helvetica", size=11)
        safe = text.encode("latin-1", errors="replace").decode("latin-1")
        if safe != text:
            options.setdefault("_warnings", []).append(
                "Nenhuma fonte Unicode encontrada; alguns caracteres viraram \"?\"."
            )
        text = safe

    pdf.multi_cell(0, 6, text, wrapmode="CHAR")
    pdf.output(str(dst))


@register(["md"], ["html"], category="Documento", notes="Markdown com tabelas e blocos de código.")
def md_to_html(src: Path, dst: Path, options: dict) -> None:
    import markdown

    body = markdown.markdown(_read_text(src, options), extensions=["tables", "fenced_code"])
    title = html.escape(src.stem)
    dst.write_text(
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n",
        encoding="utf-8",
    )
