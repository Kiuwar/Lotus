"""PDF como origem: conteúdo das saídas, casos de erro e o Word (simulado)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from conversor.core import engine
from conversor.core.engine import ConversionError, convert_file

from .conftest import make_docx, make_pdf


def _pdf(tmp_path, paginas, nome="doc.pdf"):
    return make_pdf(tmp_path / nome, paginas)


# ---------- PDF -> imagens ----------

def test_multipage_pdf_becomes_folder_with_one_image_per_page(tmp_path):
    src = _pdf(tmp_path, ["um", "dois", "três"])
    res = convert_file(src, "png", out_dir=tmp_path / "o")
    assert res.output.is_dir() and res.output.name == "doc - páginas PNG"
    nomes = sorted(p.name for p in res.output.iterdir())
    assert nomes == ["pagina_001.png", "pagina_002.png", "pagina_003.png"]
    with Image.open(res.output / "pagina_001.png") as im:
        # A4 = 595 x 842 pontos; a 150 DPI: 595*150/72 ≈ 1240, 842*150/72 ≈ 1754
        assert abs(im.size[0] - 1240) <= 2 and abs(im.size[1] - 1754) <= 2


def test_page_image_is_not_blank(tmp_path):
    src = _pdf(tmp_path, ["TEXTO GRANDE"])
    out = convert_file(src, "png", out_dir=tmp_path / "o").output
    with Image.open(out) as im:
        menor, _ = im.convert("L").getextrema()
        assert menor < 100, "a página renderizada deveria ter texto escuro, não só branco"


def test_single_page_pdf_becomes_single_file(tmp_path):
    src = _pdf(tmp_path, ["só uma"])
    res = convert_file(src, "jpg", out_dir=tmp_path / "o")
    assert res.output.is_file() and res.output.name == "doc.jpg"
    with Image.open(res.output) as im:
        assert im.format == "JPEG"


def test_existing_folder_is_never_overwritten(tmp_path):
    src = _pdf(tmp_path, ["a", "b"])
    out = tmp_path / "o"
    primeira = convert_file(src, "png", out_dir=out).output
    segunda = convert_file(src, "png", out_dir=out, overwrite=True).output
    assert primeira.name == "doc - páginas PNG" and segunda.name == "doc - páginas PNG (1)"


def test_dpi_option_changes_size(tmp_path):
    src = _pdf(tmp_path, ["x"])
    out = convert_file(src, "png", out_dir=tmp_path / "o", options={"dpi": 72}).output
    with Image.open(out) as im:
        assert abs(im.size[0] - 595) <= 2


def test_failure_mid_render_leaves_nothing(tmp_path, monkeypatch):
    src = _pdf(tmp_path, ["a", "b", "c"])
    out = tmp_path / "o"
    original = Image.Image.save
    chamadas = {"n": 0}

    def quebra_na_segunda(self, *a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise OSError("disco falhou")
        return original(self, *a, **k)

    monkeypatch.setattr(Image.Image, "save", quebra_na_segunda)
    with pytest.raises(ConversionError):
        convert_file(src, "png", out_dir=out)
    assert list(out.iterdir()) == [], "nenhuma pasta parcial pode sobrar"


# ---------- PDF -> TXT ----------

def test_pdf_to_txt_keeps_accents_and_pages(tmp_path):
    src = _pdf(tmp_path, ["Página 1: ação e coração", "Página 2: São Paulo"])
    texto = convert_file(src, "txt", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert "--- Página 1 ---" in texto and "--- Página 2 ---" in texto
    assert "ação e coração" in texto and "São Paulo" in texto


def test_scanned_pdf_without_text_fails_clearly(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.rect(10, 10, 80, 80, style="F")  # só desenho, nenhum texto
    src = tmp_path / "escaneado.pdf"
    pdf.output(str(src))
    out = tmp_path / "o"
    with pytest.raises(ConversionError, match="escaneado"):
        convert_file(src, "txt", out_dir=out)
    assert not list(out.iterdir())


@pytest.mark.parametrize("alvo", ["png", "txt"])
def test_password_protected_pdf_explains_fix(tmp_path, alvo):
    from pypdf import PdfWriter

    src = _pdf(tmp_path, ["segredo"], "aberto.pdf")
    w = PdfWriter(clone_from=str(src))
    w.encrypt(user_password="senha", owner_password="dono")
    protegido = tmp_path / "protegido.pdf"
    with open(protegido, "wb") as f:
        w.write(f)
    with pytest.raises(ConversionError, match="protegido por senha.*Como resolver"):
        convert_file(protegido, alvo, out_dir=tmp_path / "o")


def test_owner_only_protection_still_converts(tmp_path):
    from pypdf import PdfWriter

    src = _pdf(tmp_path, ["liberado"], "aberto.pdf")
    w = PdfWriter(clone_from=str(src))
    w.encrypt(user_password="", owner_password="dono")  # só impede edição
    dono = tmp_path / "dono.pdf"
    with open(dono, "wb") as f:
        w.write(f)
    assert "liberado" in convert_file(dono, "txt", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert convert_file(dono, "png", out_dir=tmp_path / "o").output.is_file()


# ---------- Word (simulado: não há Word no CI) ----------

class FakeDoc:
    def __init__(self, log, falhar=False):
        self.log, self.falhar = log, falhar

    def SaveAs2(self, FileName, FileFormat, AddToRecentFiles):
        self.log.append(("SaveAs2", FileFormat))
        if self.falhar:
            raise RuntimeError("Word recusou")
        # O Word de verdade gravaria o arquivo; aqui gravamos uma saída válida.
        if FileFormat == 17:
            make_pdf(Path(FileName), ["convertido"])
        else:
            make_docx(Path(FileName), "convertido")

    def Close(self, SaveChanges):
        self.log.append(("Close", SaveChanges))


class FakeWord:
    def __init__(self, log, falhar=False):
        self.log, self.falhar = log, falhar
        outer = self

        class Docs:
            def Open(self, FileName, ConfirmConversions, ReadOnly, AddToRecentFiles):
                outer.log.append(("Open", ReadOnly, ConfirmConversions))
                return FakeDoc(outer.log, outer.falhar)

        self.Documents = Docs()

    def __setattr__(self, k, v):
        if k in ("Visible", "DisplayAlerts"):
            self.log.append((k, v))
        object.__setattr__(self, k, v)

    def Quit(self, SaveChanges):
        self.log.append(("Quit", SaveChanges))


@pytest.fixture
def fake_word(monkeypatch):
    from conversor.converters import office

    log: list = []
    estado = {"falhar": False}
    monkeypatch.setattr(office, "word_disponivel", lambda: True)
    monkeypatch.setattr(office, "_criar_word", lambda: FakeWord(log, estado["falhar"]))
    monkeypatch.setattr(office, "_com_iniciar", lambda: log.append(("CoInitialize",)))
    monkeypatch.setattr(office, "_com_encerrar", lambda: log.append(("CoUninitialize",)))
    monkeypatch.setattr(office, "_pids_word", lambda: set())
    from conversor.core import registry

    for par in (("docx", "pdf"), ("pdf", "docx")):
        conv = registry.find(*par)
        monkeypatch.setitem(registry._REGISTRY, par, conv.__class__(**{**conv.__dict__, "available": lambda: True}))
    return log, estado


def test_docx_to_pdf_uses_word_correctly(tmp_path, sample, fake_word):
    log, _ = fake_word
    res = convert_file(sample("docx"), "pdf", out_dir=tmp_path / "o")
    assert res.output.read_bytes().startswith(b"%PDF-")
    assert log == [
        ("CoInitialize",), ("Visible", False), ("DisplayAlerts", 0),
        ("Open", True, False), ("SaveAs2", 17), ("Close", 0), ("Quit", 0), ("CoUninitialize",),
    ]


def test_pdf_to_docx_warns_about_layout(tmp_path, sample, fake_word):
    log, _ = fake_word
    res = convert_file(sample("pdf"), "docx", out_dir=tmp_path / "o")
    assert ("SaveAs2", 16) in log
    assert any("layout" in w for w in res.warnings)


def test_word_is_closed_even_when_it_fails(tmp_path, sample, fake_word):
    log, estado = fake_word
    estado["falhar"] = True
    with pytest.raises(ConversionError, match="Word não conseguiu"):
        convert_file(sample("docx"), "pdf", out_dir=tmp_path / "o")
    assert ("Close", 0) in log and ("Quit", 0) in log and log[-1] == ("CoUninitialize",)


def test_word_timeout_kills_only_our_instance(monkeypatch, tmp_path, sample):
    import threading

    from conversor.converters import office

    mortos = []
    chamadas = iter([{111}, {111, 222}])  # 111 já estava aberto pelo usuário; 222 é nosso
    liberar = threading.Event()

    class WordTravado(FakeWord):
        def __init__(self):
            super().__init__([])
            outer = self

            class Docs:
                def Open(self, **k):
                    liberar.wait(5)  # simula o Word preso num aviso invisível
                    raise RuntimeError("chamada COM interrompida")

            object.__setattr__(outer, "Documents", Docs())

    monkeypatch.setattr(office, "_criar_word", WordTravado)
    monkeypatch.setattr(office, "_com_iniciar", lambda: None)
    monkeypatch.setattr(office, "_com_encerrar", lambda: None)
    monkeypatch.setattr(office, "_pids_word", lambda: next(chamadas))

    def matar(pids):
        mortos.append(set(pids))
        liberar.set()

    monkeypatch.setattr(office, "_encerrar_pids", matar)
    src = sample("docx")
    with pytest.raises(ConversionError, match="não terminou.*Salvar como"):
        office._converter_com_word(src, tmp_path / "x.pdf", 17, limite=0.2)
    assert mortos == [{222}], "só a instância aberta pelo Lotus pode ser encerrada"


def test_word_unavailable_off_windows():
    from conversor.converters import office

    office.word_disponivel.cache_clear()
    if os.name != "nt":
        assert office.word_disponivel() is False
