"""PDF escaneado → TXT por OCR. A lógica roda com um OCR simulado (qualquer
sistema); o OCR de verdade (Windows.Media.Ocr / Vision) roda no CI do
Windows e do Mac, com um PDF que só tem a IMAGEM do texto."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from conversor import ocr
from conversor.core.engine import ConversionError, convert_file

so_win_mac = pytest.mark.skipif(sys.platform not in ("win32", "darwin"),
                                reason="OCR do sistema só no Windows e no Mac")


def pdf_escaneado(caminho: Path, paginas: list[str | None]) -> Path:
    """PDF só com imagens (como um escaneamento). None = página com texto de verdade."""
    from conversor.converters.documents import _FONT_CANDIDATES

    fonte_arq = next((p for p in _FONT_CANDIDATES if p.is_file()), None)
    fonte = ImageFont.truetype(str(fonte_arq), 64) if fonte_arq else ImageFont.load_default(64)
    imagens = []
    for texto in paginas:
        img = Image.new("RGB", (1240, 1754), "white")  # A4 a 150 DPI
        if texto:
            d = ImageDraw.Draw(img)
            for i, linha in enumerate(texto.split("\n")):
                d.text((100, 150 + i * 110), linha, font=fonte, fill="black")
        imagens.append(img)
    imagens[0].save(caminho, format="PDF", save_all=True, append_images=imagens[1:], resolution=150)
    return caminho


class OcrFalso:
    def __init__(self, textos, aviso=None):
        self.textos, self.aviso, self.chamadas = list(textos), aviso, []

    def reconhecer(self, imagem):
        self.chamadas.append(imagem.size)
        return self.textos.pop(0)


@pytest.fixture
def ocr_falso(monkeypatch):
    def usar(textos, aviso=None):
        falso = OcrFalso(textos, aviso)
        monkeypatch.setattr(ocr, "_backend", lambda: falso)
        return falso
    return usar


def test_scanned_pdf_becomes_text_with_warning(tmp_path, ocr_falso):
    falso = ocr_falso(["Petição inicial\nAção de cobrança", "Página dois"])
    src = pdf_escaneado(tmp_path / "tese.pdf", ["x", "y"])
    r = convert_file(src, "txt", out_dir=tmp_path / "o")
    txt = r.output.read_text(encoding="utf-8")
    assert "--- Página 1 ---\nPetição inicial\nAção de cobrança" in txt and "Página dois" in txt
    assert any("2 página(s) escaneada(s)" in w and "Confira" in w for w in r.warnings)
    assert falso.chamadas[0][1] > 3000, "página renderizada a 300 DPI para o OCR"


def test_only_pages_without_text_go_to_ocr(tmp_path, ocr_falso):
    from .conftest import make_pdf

    falso = ocr_falso(["não deve ser usado"])
    src = make_pdf(tmp_path / "normal.pdf", ["Página 1: ação e coração"])
    txt = convert_file(src, "txt", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert "ação e coração" in txt and falso.chamadas == [], "texto de verdade não passa por OCR"


def test_language_warning_is_passed_on(tmp_path, ocr_falso):
    ocr_falso(["Texto"], aviso="O reconhecimento em português não está instalado no Windows")
    r = convert_file(pdf_escaneado(tmp_path / "a.pdf", ["x"]), "txt", out_dir=tmp_path / "o")
    assert any("português não está instalado" in w for w in r.warnings)


def test_ocr_that_reads_nothing_explains(tmp_path, ocr_falso):
    ocr_falso([""])
    with pytest.raises(ConversionError, match="nem por OCR"):
        convert_file(pdf_escaneado(tmp_path / "branco.pdf", [None]), "txt", out_dir=tmp_path / "o")


def test_without_ocr_explains_which_systems_have_it(tmp_path, monkeypatch):
    def sem():
        raise ocr.OcrIndisponivel(ocr.motivo())

    monkeypatch.setattr(ocr, "_backend", sem)
    with pytest.raises(ConversionError, match="escaneado"):
        convert_file(pdf_escaneado(tmp_path / "a.pdf", ["x"]), "txt", out_dir=tmp_path / "o")


# ---------- OCR de verdade (CI do Windows e do Mac) ----------

@so_win_mac
def test_real_system_ocr_reads_a_scanned_pdf(tmp_path):
    ocr._backend.cache_clear()
    if not ocr.disponivel():
        pytest.fail(f"OCR do sistema indisponível no CI: {ocr.motivo()}")
    src = pdf_escaneado(tmp_path / "escaneado.pdf", ["LOTUS CONVERTE ARQUIVOS\nCODIGO 2026"])
    r = convert_file(src, "txt", out_dir=tmp_path / "o")
    txt = r.output.read_text(encoding="utf-8").upper()
    print(txt, r.warnings)
    assert "LOTUS" in txt and "2026" in txt


@pytest.mark.skipif(sys.platform != "darwin", reason="só no macOS")
def test_vision_names_exist():
    import Vision

    assert not [n for n in ocr.NOMES_VISION if not hasattr(Vision, n)]
