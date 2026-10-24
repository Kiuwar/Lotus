"""Conversões com PDF como origem.

- PDF → PNG/JPG: uma imagem por página, renderizada pelo PDFium (pypdfium2,
  o mesmo motor de PDF do Chrome). Fiel ao original.
- PDF → TXT: texto extraído com pypdf. Páginas escaneadas (só imagem) passam
  pelo OCR do próprio sistema (conversor/ocr.py: Windows 10/11 e Mac), com
  aviso. Sem OCR e sem texto, a conversão falha explicando, em vez de gerar
  um .txt vazio.
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


OCR_DPI = 300  # resolução usada só para reconhecer texto (escaneados costumam ter 200–300)


def _ocr_paginas(src: Path, numeros: list[int], options: dict) -> dict[int, str]:
    """Texto por OCR das páginas indicadas (base 1). {} se não houver OCR."""
    from conversor import ocr

    if not ocr.disponivel():
        return {}
    doc = _abrir_pdfium(src)
    textos: dict[int, str] = {}
    aviso_idioma = None
    try:
        for n in numeros:
            pagina = doc[n - 1]
            try:
                img = pagina.render(scale=OCR_DPI / 72).to_pil()
            finally:
                pagina.close()
            texto, aviso_idioma = ocr.reconhecer(img)
            textos[n] = texto.strip()
    finally:
        doc.close()
    if aviso_idioma:
        options.setdefault("_warnings", []).append(aviso_idioma)
    return textos


@register(["pdf"], ["txt"], category="PDF",
          notes="Texto do PDF; páginas escaneadas passam por OCR (Windows 10/11 e Mac).")
def pdf_para_txt(src: Path, dst: Path, options: dict) -> None:
    from pypdf import PdfReader

    from conversor import ocr

    leitor = PdfReader(str(src))
    if leitor.is_encrypted and not leitor.decrypt(""):
        # decrypt("") resolve PDFs que só têm senha de "dono" (proteção contra edição).
        raise ConversionError(SENHA.format(nome=src.name))
    textos = [(pagina.extract_text() or "").strip() for pagina in leitor.pages]
    sem_texto = [n for n, t in enumerate(textos, start=1) if not t]
    lidas = _ocr_paginas(src, sem_texto, options) if sem_texto else {}
    for n, t in lidas.items():
        textos[n - 1] = t
    avisos = options.setdefault("_warnings", [])
    if lidas:
        avisos.append(f"{src.name}: {len(lidas)} página(s) escaneada(s) lida(s) por OCR (reconhecimento "
                      "de texto). Confira nomes, números e acentos: o OCR pode errar.")
    if not any(textos):
        if sem_texto and not lidas:
            raise ConversionError(
                f"{src.name} não tem texto selecionável (provavelmente é escaneado) e {ocr.motivo()}. "
                "Converta para PNG/JPG para ver as páginas.")
        raise ConversionError(f"{src.name}: nenhum texto foi encontrado, nem por OCR "
                              "(páginas em branco ou imagem ilegível).")
    vazias = [n for n, t in enumerate(textos, start=1) if not t]
    if vazias:
        avisos.append(f"{src.name}: {len(vazias)} página(s) sem texto (em branco ou ilegíveis) ficaram vazias.")
    partes = [f"--- Página {n} ---\n{t}" for n, t in enumerate(textos, start=1)]
    dst.write_text("\n\n".join(partes) + "\n", encoding="utf-8")
