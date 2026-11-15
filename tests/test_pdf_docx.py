"""PDF → DOCX: relato real da 0.11.0 — o Word abriu o PDF como TEXTO e o DOCX
saiu com o código do PDF ("%PDF-1.4 … obj … endobj"). Word simulado (regra 17)."""

import hashlib
from pathlib import Path

from conversor.converters import office
from conversor.converters.docx_escrita import escrever_docx
from conversor.converters.office_texto import Bloco, Trecho
from conversor.core import validate
from tests.conftest import make_pdf

PAGINAS = ["UNIDADE AVANCADA DE ATENDIMENTO judiciario Itapeva valor causa",
           "Requerente reclamacao contrato anulacao danos morais embratel"]


def _docx_com(texto: str, dst: Path) -> Path:
    escrever_docx([Bloco("par", [Trecho(texto)])], dst, "x")
    return dst


def test_validador_recusa_docx_com_bytes_de_pdf(tmp_path):
    lixo = "%PDF-1.4 % 1 0 obj <</Producer(Skia)>> endobj " + "2 0 obj <<>> endobj " * 30
    problema = validate.check(_docx_com(lixo, tmp_path / "a.docx"), "docx")
    assert problema and "código interno de um PDF" in problema


def test_validador_aceita_docx_normal(tmp_path):
    assert validate.check(_docx_com("Um texto jurídico comum.", tmp_path / "a.docx"), "docx") is None


def test_word_que_devolve_lixo_cai_no_plano_b(tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "NPJ dia 21.PDF", PAGINAS)
    antes = hashlib.sha256(src.read_bytes()).hexdigest()
    abertos = []

    def word_falso(origem, destino, formato, limite=0):
        abertos.append(origem)
        assert origem.name == "entrada.pdf" and origem != src  # cópia curta, minúscula
        _docx_com("%PDF-1.4 " + "1 0 obj endobj " * 40, destino)

    monkeypatch.setattr(office, "_converter_com_word", word_falso)
    dst = tmp_path / "saida.docx"
    opcoes: dict = {}
    office.pdf_para_docx(src, dst, opcoes)
    texto = validate.docx_texto(dst)
    assert "UNIDADE AVANCADA DE ATENDIMENTO" in texto and "embratel" in texto
    assert "%PDF" not in texto
    assert any("só com o TEXTO do PDF" in a for a in opcoes["_warnings"])
    assert not abertos[0].exists()  # cópia temporária apagada
    assert hashlib.sha256(src.read_bytes()).hexdigest() == antes


def test_word_que_funciona_mantem_resultado(tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "a.pdf", PAGINAS)
    monkeypatch.setattr(office, "_converter_com_word",
                        lambda o, d, f, limite=0: _docx_com(" ".join(PAGINAS) + " WORD", d))
    dst = tmp_path / "saida.docx"
    opcoes: dict = {}
    office.pdf_para_docx(src, dst, opcoes)
    assert "WORD" in validate.docx_texto(dst)
    assert any("Word reconstrói" in a for a in opcoes["_warnings"])


def test_word_com_erro_cai_no_plano_b(tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "a.pdf", PAGINAS)

    def falha(*_a, **_k):
        raise office.ConversionError("O Word não conseguiu converter")

    monkeypatch.setattr(office, "_converter_com_word", falha)
    dst = tmp_path / "saida.docx"
    office.pdf_para_docx(src, dst, {})
    assert "Requerente" in validate.docx_texto(dst)


def test_paragrafos_juntam_linhas_quebradas():
    texto = ("O autor iniciou a reclamação junto à empresa, que não\r\n"
             "resolveu o problema apresentado no prazo legal.\r\n"
             "DOS FATOS\r\nCurto\r\n")
    assert office.paragrafos(texto) == [
        "O autor iniciou a reclamação junto à empresa, que não resolveu o problema apresentado no prazo legal.",
        "DOS FATOS", "Curto"]
