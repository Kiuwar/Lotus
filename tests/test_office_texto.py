"""DOCX/PPTX → texto sem Office, novos formatos do Office e PowerPoint (simulado)."""

from __future__ import annotations

import pytest

from conversor.core.detect import DetectionError, detect
from conversor.core.engine import ConversionError, convert_file

from .conftest import make_docx_rico, make_opendocument, make_pptx

# ---------- DOCX sem Word ----------


def test_docx_to_markdown_keeps_structure(tmp_path):
    src = make_docx_rico(tmp_path / "peticao.docx")
    r = convert_file(src, "md", out_dir=tmp_path / "o")
    md = r.output.read_text(encoding="utf-8")
    assert "# Petição inicial" in md, "estilo com ID localizado (Ttulo1) vira título"
    assert "**negrito**" in md and "*itálico*" in md
    assert "[o site](https://exemplo.com.br/a%20b)" in md
    assert "1. Primeiro pedido\n1. Segundo pedido" in md, "lista numerada (numFmt decimal)"
    assert "1. Segundo pedido\n\n- Tópico solto" in md, "troca de lista separada por linha em branco"
    assert "\n\n\n" not in md, "sem linhas em branco duplicadas"
    assert "| Nome | Valor |" in md and "| Custas | R$ 10,50 |" in md
    assert "apagado" not in md, "texto apagado (controle de alterações) não aparece"
    assert "Fim" in md
    avisos = " ".join(r.warnings)
    assert "1 imagem" in avisos and "rodapé" in avisos and "fontes" in avisos


def test_docx_to_txt_numbers_list_and_tabs_table(tmp_path):
    src = make_docx_rico(tmp_path / "peticao.docx")
    txt = convert_file(src, "txt", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert "1. Primeiro pedido\n2. Segundo pedido" in txt
    assert "• Tópico solto" in txt
    assert "Custas\tR$ 10,50" in txt
    assert "Texto com negrito e itálico, veja o site." in txt


def test_docx_to_html_is_valid_utf8_with_lists_and_table(tmp_path):
    from html.parser import HTMLParser

    src = make_docx_rico(tmp_path / "peticao.docx")
    html = convert_file(src, "html", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert '<meta charset="utf-8">' in html and "<h1>Petição inicial</h1>" in html
    assert "<ol><li>Primeiro pedido</li><li>Segundo pedido</li></ol>" in html.replace("\n", "")
    assert "<strong>negrito</strong>" in html and 'href="https://exemplo.com.br/a b"' in html
    assert "<td>R$ 10,50</td>" in html

    class Contador(HTMLParser):
        def __init__(self):
            super().__init__()
            self.pilha = []

        def handle_starttag(self, tag, attrs):
            if tag in ("ol", "ul", "li", "table", "tr", "td", "p", "h1", "strong", "em", "a"):
                self.pilha.append(tag)

        def handle_endtag(self, tag):
            if tag in ("ol", "ul", "li", "table", "tr", "td", "p", "h1", "strong", "em", "a"):
                assert self.pilha and self.pilha[-1] == tag, f"</{tag}> fora de ordem"
                self.pilha.pop()

    c = Contador()
    c.feed(html)
    assert c.pilha == [], "toda tag aberta foi fechada"


def test_docx_text_escapes_markdown_and_html_special_chars(tmp_path):
    from .conftest import make_docx

    src = make_docx(tmp_path / "a.docx", "Use *asterisco* e <tag> & 50% | barra")
    md = convert_file(src, "md", out_dir=tmp_path / "m").output.read_text(encoding="utf-8")
    html = convert_file(src, "html", out_dir=tmp_path / "h").output.read_text(encoding="utf-8")
    assert r"\*asterisco\*" in md and r"\<tag\>" in md and r"\|" in md
    assert "&lt;tag&gt; &amp; 50%" in html


def test_broken_docx_explains(tmp_path):
    ruim = tmp_path / "ruim.docx"
    import zipfile

    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("word/document.xml", "<isto não é xml")
    with pytest.raises(ConversionError):
        convert_file(ruim, "txt", out_dir=tmp_path / "o")


# ---------- PPTX sem PowerPoint ----------


def test_pptx_to_markdown_has_slides_bullets_table_and_notes(tmp_path):
    src = make_pptx(tmp_path / "aula.pptx")
    r = convert_file(src, "md", out_dir=tmp_path / "o")
    md = r.output.read_text(encoding="utf-8")
    assert "## Slide 1: Audiência de conciliação" in md
    assert "- Pauta do dia\n    - Proposta de acordo" in md, "recuo do tópico (lvl=1)"
    assert "> **Notas:** Lembrar do prazo" in md
    assert "## Slide 2: Valores (oculto)" in md and "| Item | R$ |" in md
    assert md.index("Slide 1") < md.index("Slide 2"), "ordem dos slides da apresentação"
    assert any("1 imagem" in w for w in r.warnings)


def test_pptx_to_txt(tmp_path):
    src = make_pptx(tmp_path / "aula.pptx")
    txt = convert_file(src, "txt", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert "Slide 1: Audiência de conciliação" in txt and "Notas: Lembrar do prazo" in txt
    assert "  • Proposta de acordo" in txt


# ---------- reconhecimento dos formatos do Office ----------


@pytest.mark.parametrize("fmt", ["pptx", "odt", "odp", "rtf"])
def test_office_formats_detected_by_content(sample, fmt):
    assert detect(sample(fmt)).fmt == fmt


def test_old_office_files_use_the_extension(tmp_path):
    ole = bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 56
    for ext in ("doc", "ppt"):
        p = tmp_path / f"a.{ext}"
        p.write_bytes(ole)
        assert detect(p).fmt == ext
    p = tmp_path / "a.bin"
    p.write_bytes(ole)
    with pytest.raises(DetectionError, match="Office antigo"):
        detect(p)


def test_opendocument_text_is_not_mistaken_for_presentation(tmp_path):
    t = make_opendocument(tmp_path / "x.odt", "application/vnd.oasis.opendocument.text")
    p = make_opendocument(tmp_path / "y.odp", "application/vnd.oasis.opendocument.presentation")
    assert detect(t).fmt == "odt" and detect(p).fmt == "odp"


def test_new_office_outputs_are_validated(tmp_path):
    from conversor.core.validate import check

    rtf = tmp_path / "a.rtf"
    rtf.write_bytes(b"{\\rtf1 ok}")
    assert check(rtf, "rtf") is None
    falso = tmp_path / "b.pptx"
    falso.write_bytes(b"nada")
    assert check(falso, "pptx") is not None


# ---------- PowerPoint (simulado: o CI não tem Office) ----------


class FakeSlide:
    def __init__(self, log, i):
        self.log, self.i = log, i

    def Export(self, nome, filtro, largura, altura):
        self.log.append(("Export", self.i, filtro, largura, altura))
        from PIL import Image

        Image.new("RGB", (largura, altura), (200, 50, 50)).save(nome, format=filtro.replace("JPG", "JPEG"))


class FakePres:
    def __init__(self, log, slides, falhar):
        self.log, self.falhar = log, falhar
        outer = self

        class Slides:
            Count = slides

            def Item(self, i):
                return FakeSlide(outer.log, i)

        class Setup:
            SlideWidth, SlideHeight = 960.0, 540.0

        self.Slides, self.PageSetup = Slides(), Setup()

    def SaveAs(self, FileName, FileFormat):
        self.log.append(("SaveAs", FileFormat))
        if self.falhar:
            raise RuntimeError("falha simulada")
        from pathlib import Path

        conteudo = {32: b"%PDF-1.4\n%%EOF\n"}.get(FileFormat, b"")
        if FileFormat in (24,):
            import zipfile

            with zipfile.ZipFile(FileName, "w") as z:
                z.writestr("ppt/presentation.xml", "<p/>")
            return
        Path(FileName).write_bytes(conteudo or bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 56)

    def Close(self):
        self.log.append(("Close",))


class FakePowerPoint:
    def __init__(self, log, slides=2, falhar=False):
        self.log = log
        outer = self

        class Pres:
            def Open(self, FileName, ReadOnly, Untitled, WithWindow):
                outer.log.append(("Open", ReadOnly, Untitled, WithWindow))
                return FakePres(outer.log, slides, falhar)

        self.Presentations = Pres()

    def Quit(self):
        self.log.append(("Quit",))


@pytest.fixture
def fake_pp(monkeypatch):
    from conversor.converters import office
    from conversor.core import registry

    log: list = []
    estado = {"slides": 2, "falhar": False}
    monkeypatch.setattr(office, "_criar_powerpoint",
                        lambda: FakePowerPoint(log, estado["slides"], estado["falhar"]))
    monkeypatch.setattr(office, "_com_iniciar", lambda: log.append(("CoInitialize",)))
    monkeypatch.setattr(office, "_com_encerrar", lambda: log.append(("CoUninitialize",)))
    monkeypatch.setattr(office, "_pids_powerpoint", lambda: set())
    for par in (("pptx", "pdf"), ("pptx", "png"), ("pptx", "jpg"), ("pptx", "ppt")):
        conv = registry.find(*par)
        monkeypatch.setitem(registry._REGISTRY, par, conv.__class__(**{**conv.__dict__, "available": lambda: True}))
    return log, estado


def test_pptx_to_pdf_uses_powerpoint_correctly(tmp_path, sample, fake_pp):
    log, _ = fake_pp
    r = convert_file(sample("pptx"), "pdf", out_dir=tmp_path / "o")
    assert r.output.read_bytes().startswith(b"%PDF-")
    # ReadOnly=msoTrue (-1), Untitled=msoFalse (0), WithWindow=msoFalse (0); ppSaveAsPDF = 32
    assert log == [("CoInitialize",), ("Open", -1, 0, 0), ("SaveAs", 32), ("Close",), ("Quit",),
                   ("CoUninitialize",)]


def test_pptx_to_old_ppt_uses_format_1(tmp_path, sample, fake_pp):
    log, _ = fake_pp
    r = convert_file(sample("pptx"), "ppt", out_dir=tmp_path / "o")
    assert ("SaveAs", 1) in log and r.output.suffix == ".ppt"


@pytest.mark.parametrize("alvo", ["png", "jpg"])
def test_pptx_to_images_one_per_slide_full_hd(tmp_path, sample, fake_pp, alvo):
    log, estado = fake_pp
    estado["slides"] = 3
    r = convert_file(sample("pptx"), alvo, out_dir=tmp_path / "o")
    arquivos = sorted(p.name for p in r.output.iterdir())
    assert arquivos == [f"slide_00{i}.{alvo}" for i in (1, 2, 3)]
    assert ("Export", 1, alvo.upper(), 1920, 1080) in log, "proporção 16:9 do slide"


def test_powerpoint_is_closed_even_when_it_fails(tmp_path, sample, fake_pp):
    log, estado = fake_pp
    estado["falhar"] = True
    with pytest.raises(ConversionError, match="PowerPoint não conseguiu"):
        convert_file(sample("pptx"), "pdf", out_dir=tmp_path / "o")
    assert ("Close",) in log and ("Quit",) in log and log[-1] == ("CoUninitialize",)


def test_empty_presentation_to_images_explains(tmp_path, sample, fake_pp):
    _, estado = fake_pp
    estado["slides"] = 0
    with pytest.raises(ConversionError, match="não tem slides"):
        convert_file(sample("pptx"), "png", out_dir=tmp_path / "o")


def test_office_conversions_unavailable_without_office():
    import sys

    from conversor.converters import office

    office.powerpoint_disponivel.cache_clear()
    if sys.platform != "win32":
        assert office.powerpoint_disponivel() is False
