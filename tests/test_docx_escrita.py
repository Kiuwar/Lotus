"""TXT/MD/HTML → DOCX/PDF e DOCX → PDF sem Word; Word × textutil do Mac.

O DOCX gravado pelo Lotus é conferido com o python-docx (leitor independente,
só nos testes), não com o leitor do próprio Lotus.
"""

from __future__ import annotations

import sys
import zipfile

import pytest

from conversor.core.engine import ConversionError, convert_file

docx = pytest.importorskip("docx", reason="python-docx confere os DOCX gravados")

MD = """# Petição inicial

Texto com **negrito**, *itálico* e [link](https://exemplo.com.br/a).

1. Primeiro pedido
2. Segundo pedido
    - detalhe

Parágrafo entre listas.

1. Outra lista

| Nome | Valor |
|------|-------|
| Custas | R$ 10,50 |

```
codigo   com  espacos
```
"""


def _pdf_texto(caminho) -> str:
    from pypdf import PdfReader

    return "\n".join(p.extract_text() for p in PdfReader(str(caminho)).pages)


def test_markdown_to_docx_has_word_styles_lists_table_and_link(tmp_path):
    src = tmp_path / "peticao.md"
    src.write_text(MD, encoding="utf-8")
    r = convert_file(src, "docx", out_dir=tmp_path / "o")
    d = docx.Document(str(r.output))
    paras = [(p.style.name, p.text) for p in d.paragraphs if p.text]
    assert paras[0] == ("Heading 1", "Petição inicial"), "título vira o estilo Título 1 do Word"
    corpo = d.paragraphs[1]
    assert corpo.text == "Texto com negrito, itálico e link."
    assert any(run.bold and run.text == "negrito" for run in corpo.runs)
    assert any(run.italic and run.text == "itálico" for run in corpo.runs)
    assert ("List Paragraph", "Primeiro pedido") in paras and ("List Paragraph", "detalhe") in paras
    assert ("Código", "codigo   com  espacos") in paras, "bloco de código mantém os espaços"
    tabela = d.tables[0]
    assert [c.text for c in tabela.rows[1].cells] == ["Custas", "R$ 10,50"]
    assert tabela.rows[0].cells[0].paragraphs[0].runs[0].bold, "cabeçalho da tabela em negrito"
    links = [rel.target_ref for rel in d.part.rels.values() if rel.reltype.endswith("/hyperlink")]
    assert links == ["https://exemplo.com.br/a"]
    assert d.core_properties.title == "peticao"


def test_each_numbered_list_restarts_at_one(tmp_path):
    src = tmp_path / "a.md"
    src.write_text(MD, encoding="utf-8")
    out = convert_file(src, "docx", out_dir=tmp_path / "o").output
    with zipfile.ZipFile(out) as z:
        doc = z.read("word/document.xml").decode()
        num = z.read("word/numbering.xml").decode()
    assert num.count("<w:startOverride w:val=\"1\"/>") == 2, "duas listas numeradas, cada uma do 1"
    assert '<w:numId w:val="2"/>' in doc and '<w:numId w:val="3"/>' in doc
    assert '<w:numId w:val="1"/>' in doc, "o subitem com marcador usa a lista de marcadores"


def test_docx_written_by_lotus_reads_back_the_same_structure(tmp_path):
    src = tmp_path / "a.md"
    src.write_text(MD, encoding="utf-8")
    meio = convert_file(src, "docx", out_dir=tmp_path / "o").output
    md = convert_file(meio, "md", out_dir=tmp_path / "v").output.read_text(encoding="utf-8")
    assert "# Petição inicial" in md and "**negrito**" in md
    assert "1. Primeiro pedido\n1. Segundo pedido\n    - detalhe" in md
    assert "| Custas | R$ 10,50 |" in md


def test_html_to_docx_drops_scripts_and_unsafe_links(tmp_path, sample):
    r = convert_file(sample("html"), "docx", out_dir=tmp_path / "o")
    d = docx.Document(str(r.output))
    texto = "\n".join(p.text for p in d.paragraphs)
    assert "alert" not in texto and "color: red" not in texto, "script e CSS não viram texto"
    assert "Partes: Ana e João, ver termos e não clique." in texto
    links = [rel.target_ref for rel in d.part.rels.values() if rel.reltype.endswith("/hyperlink")]
    assert links == ["https://exemplo.com.br/termos"], "javascript: não vira link"
    assert d.paragraphs[0].style.name == "Heading 1"
    assert [c.text for c in d.tables[0].rows[0].cells] == ["Item", "Valor"]
    avisos = " ".join(r.warnings)
    assert "CSS" in avisos and "1 imagem" in avisos


def test_txt_to_docx_keeps_lines_tabs_and_removes_control_chars(tmp_path):
    src = tmp_path / "nota.txt"
    src.write_text("Linha 1\tcom tab\n\nLinha 3 ação\x0c fim\n", encoding="utf-8")
    r = convert_file(src, "docx", out_dir=tmp_path / "o")
    d = docx.Document(str(r.output))
    assert [p.text for p in d.paragraphs] == ["Linha 1\tcom tab", "", "Linha 3 ação fim"]
    assert any("controle" in w for w in r.warnings)


def test_empty_text_to_docx_explains(tmp_path):
    src = tmp_path / "vazio.md"
    src.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ConversionError, match="não tem texto"):
        convert_file(src, "docx", out_dir=tmp_path / "o")


def test_docx_to_pdf_without_word_keeps_text_and_warns(tmp_path, monkeypatch):
    from conversor.converters import office

    from .conftest import make_docx_rico

    monkeypatch.setattr(office, "word_disponivel", lambda: False)
    src = make_docx_rico(tmp_path / "peticao.docx")
    r = convert_file(src, "pdf", out_dir=tmp_path / "o")
    texto = _pdf_texto(r.output)
    for trecho in ("Petição inicial", "Primeiro pedido", "Segundo pedido", "R$ 10,50", "Fim"):
        assert trecho in texto
    assert any("sem o Word" in w for w in r.warnings)


@pytest.mark.parametrize("origem", ["md", "html"])
def test_markdown_and_html_to_pdf(tmp_path, sample, origem):
    if origem == "md":
        src = tmp_path / "a.md"
        src.write_text(MD, encoding="utf-8")
        esperado = ["Petição inicial", "Primeiro pedido", "R$ 10,50"]
    else:
        src = sample("html")
        esperado = ["Contrato de serviço", "Primeira cláusula", "R$ 10,50"]
    texto = _pdf_texto(convert_file(src, "pdf", out_dir=tmp_path / "o").output)
    assert all(e in texto for e in esperado)
    assert "alert" not in texto


def test_html_to_txt_and_md(tmp_path, sample):
    txt = convert_file(sample("html"), "txt", out_dir=tmp_path / "t").output.read_text(encoding="utf-8")
    assert "1. Primeira cláusula\n2. Segunda cláusula\n  • Subitem" in txt
    assert "Item\tValor\nTaxa\tR$ 10,50" in txt and "alert" not in txt
    md = convert_file(sample("html"), "md", out_dir=tmp_path / "m").output.read_text(encoding="utf-8")
    assert "# Contrato de serviço" in md and "[termos](https://exemplo.com.br/termos)" in md
    assert "```\ncódigo   alinhado\n```" in md


def test_broken_docx_xml_is_rejected_by_validator(tmp_path):
    from conversor.core.validate import check

    ruim = tmp_path / "ruim.docx"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document><w:body>")
    assert "XML inválido" in check(ruim, "docx")


# ---------- Word × textutil (Mac) ----------

@pytest.fixture
def textutil_simulado(monkeypatch):
    """Sem Word, com o textutil do Mac (simulado: grava a saída pedida)."""
    from conversor.converters import office

    chamadas: list[list[str]] = []

    class Resultado:
        returncode, stdout, stderr = 0, "", ""

    def run(cmd, **kw):
        chamadas.append(cmd)
        from pathlib import Path

        from .conftest import make_docx

        saida = Path(cmd[cmd.index("-output") + 1])
        if cmd[2] == "docx":
            make_docx(saida, "Petição: ação de cobrança")
        else:
            saida.write_bytes(b"{\\rtf1 ok}")
        return Resultado()

    monkeypatch.setattr(office, "word_disponivel", lambda: False)
    monkeypatch.setattr(office, "textutil_disponivel", lambda: True)
    monkeypatch.setattr(office.subprocess, "run", run)
    return chamadas


def test_without_word_mac_uses_textutil_with_documented_options(tmp_path, sample, textutil_simulado):
    r = convert_file(sample("docx"), "rtf", out_dir=tmp_path / "o")
    cmd = textutil_simulado[0]
    assert cmd[:3] == ["textutil", "-convert", "rtf"] and cmd[3] == "-output"
    assert cmd[-1].endswith("amostra.docx") and r.output.suffix == ".rtf"
    assert any("textutil" in w for w in r.warnings)


def test_rtf_to_pdf_on_mac_goes_through_docx(tmp_path, sample, textutil_simulado):
    r = convert_file(sample("rtf"), "pdf", out_dir=tmp_path / "o")
    assert textutil_simulado[0][2] == "docx"
    assert "Petição: ação de cobrança" in _pdf_texto(r.output)


def test_textutil_failure_explains_how_to_fix(tmp_path, sample, monkeypatch, textutil_simulado):
    from conversor.converters import office

    class Falha:
        returncode, stdout, stderr = 1, "", "Error reading file"

    monkeypatch.setattr(office.subprocess, "run", lambda cmd, **kw: Falha())
    with pytest.raises(ConversionError, match="textutil.*Error reading file.*Como resolver"):
        convert_file(sample("rtf"), "odt", out_dir=tmp_path / "o")


def test_word_is_preferred_over_textutil(tmp_path, sample, monkeypatch):
    from conversor.converters import office

    usados = []
    monkeypatch.setattr(office, "word_disponivel", lambda: True)
    monkeypatch.setattr(office, "textutil_disponivel", lambda: True)
    monkeypatch.setattr(office, "word_salvar_como", lambda s, d, o: (usados.append("word"),
                                                                   d.write_bytes(b"{\\rtf1 ok}")))
    convert_file(sample("docx"), "rtf", out_dir=tmp_path / "o")
    assert usados == ["word"]


@pytest.mark.skipif(sys.platform != "darwin", reason="textutil real só existe no Mac")
def test_real_textutil_rtf_to_docx_keeps_accents(tmp_path, sample):
    from conversor.converters.office_texto import ler_docx

    out = convert_file(sample("rtf"), "docx", out_dir=tmp_path / "o").output
    blocos, _ = ler_docx(out)
    assert "Petição: ação de cobrança" in " ".join(b.texto() for b in blocos)
