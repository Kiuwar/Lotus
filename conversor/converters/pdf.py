"""Conversões com PDF como origem.

- PDF → PNG/JPG: uma imagem por página, renderizada pelo PDFium (pypdfium2,
  o mesmo motor de PDF do Chrome). Fiel ao original.
- PDF → TXT: texto extraído com pypdf. PDF escaneado (só imagem) não tem
  texto: a conversão falha com explicação, em vez de gerar um .txt vazio.
"""

from __future__ import annotations

from pathlib import Path

from conversor.core.engine import ConversionError
from conversor.core.registry import register

SENHA = (
    "{nome} está protegido por senha. Como resolver: abra o PDF no seu leitor, "
    "salve/imprima uma cópia sem senha (\"Microsoft Print to PDF\") e converta a cópia."
)


def _abrir_pdfium(src: Path):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(src))
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise ConversionError(SENHA.format(nome=src.name)) from e
        raise ConversionError(f"{src.name} não pôde ser aberto como PDF ({e}).") from e


@register(["pdf"], ["png", "jpg"], category="PDF", multi=True,
          notes="Uma imagem por página (150 DPI); várias páginas vão para uma pasta.")
def pdf_para_imagens(src: Path, pasta: Path, options: dict) -> None:
    alvo = "png" if (options.get("_target") or "png") == "png" else "jpg"
    escala = float(options.get("dpi", 150)) / 72  # PDF usa 72 pontos por polegada
    doc = _abrir_pdfium(src)
    try:
        total = len(doc)
        digitos = max(3, len(str(total)))
        for i in range(total):
            pagina = doc[i]
            try:
                img = pagina.render(scale=escala).to_pil()
            finally:
                pagina.close()
            destino = pasta / f"pagina_{i + 1:0{digitos}d}.{alvo}"
            if alvo == "jpg":
                img.convert("RGB").save(destino, format="JPEG", quality=int(options.get("quality", 90)))
            else:
                img.save(destino, format="PNG")
    finally:
        doc.close()


@register(["pdf"], ["txt"], category="PDF",
          notes="Só o texto (sem layout). PDF escaneado não tem texto e não há OCR.")
def pdf_para_txt(src: Path, dst: Path, options: dict) -> None:
    from pypdf import PdfReader

    leitor = PdfReader(str(src))
    if leitor.is_encrypted and not leitor.decrypt(""):
        # decrypt("") resolve PDFs que só têm senha de "dono" (proteção contra edição).
        raise ConversionError(SENHA.format(nome=src.name))
    partes = []
    com_texto = 0
    for n, pagina in enumerate(leitor.pages, start=1):
        texto = (pagina.extract_text() or "").strip()
        if texto:
            com_texto += 1
        partes.append(f"--- Página {n} ---\n{texto}")
    if com_texto == 0:
        raise ConversionError(
            f"{src.name} não tem texto selecionável (provavelmente é escaneado). "
            "O Lotus ainda não faz OCR; converta para PNG/JPG para ver as páginas."
        )
    sem = len(leitor.pages) - com_texto
    if sem:
        options.setdefault("_warnings", []).append(
            f"{src.name}: {sem} página(s) sem texto selecionável (imagem/escaneada) ficaram vazias."
        )
    dst.write_text("\n\n".join(partes) + "\n", encoding="utf-8")
