"""Separar e juntar PDFs: testes de CONTEÚDO (o texto certo na página certa)."""

import hashlib
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from conversor.converters.pdf_paginas import interpretar_paginas
from conversor.core import engine
from conversor.core.engine import ConversionError
from conversor.core.errors import ConversaoPaginasErro
from tests.conftest import make_pdf


def _textos(pdf: Path) -> list[str]:
    return [p.extract_text() for p in PdfReader(str(pdf)).pages]


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def pdf10(tmp_path):
    return make_pdf(tmp_path / "Contrato social.pdf", [f"Pagina {n} texto" for n in range(1, 11)])


# --- intervalos -------------------------------------------------------------

def test_interpretar():
    assert interpretar_paginas("1-3, 5; 8-", 10) == [(1, 3), (5, 5), (8, 10)]
    assert interpretar_paginas(" 2 - 4 ", 10) == [(2, 4)]


@pytest.mark.parametrize("texto,trecho", [
    ("", "Nenhuma página"),
    ("12", "não existe: o PDF tem 10"),
    ("5-2", "invertido"),
    ("a-b", "não é uma página"),
    ("0", "não existe"),
])
def test_interpretar_erros(texto, trecho):
    with pytest.raises(ConversaoPaginasErro, match=trecho):
        interpretar_paginas(texto, 10)


# --- separar ----------------------------------------------------------------

def test_separar_por_intervalos(pdf10):
    antes = _hash(pdf10)
    r = engine.separar_pdf(pdf10, "1-3, 4-9, 10")
    assert [p.name for p in r.saidas] == [
        "Contrato social (p1-3).pdf", "Contrato social (p4-9).pdf", "Contrato social (p10).pdf"]
    assert r.saidas[0].parent.name == "Contrato social - partes"
    t = _textos(r.saidas[0])
    assert len(t) == 3 and "Pagina 1 " in t[0] and "Pagina 3 " in t[2]
    assert len(_textos(r.saidas[1])) == 6 and "Pagina 10 " in _textos(r.saidas[2])[0]
    assert _hash(pdf10) == antes  # original intacto


def test_extrair_paginas_na_ordem(pdf10):
    r = engine.separar_pdf(pdf10, "7, 2-3", modo=engine.SEPARAR_EXTRAIR)
    (saida,) = r.saidas
    assert saida.name == "Contrato social (p7,2-3).pdf"
    t = _textos(saida)
    assert len(t) == 3 and "Pagina 7 " in t[0] and "Pagina 2 " in t[1] and "Pagina 3 " in t[2]


def test_separar_nao_sobrescreve(pdf10):
    a = engine.separar_pdf(pdf10, "1-2").saidas[0].parent
    b = engine.separar_pdf(pdf10, "1-2").saidas[0].parent
    assert a != b and b.name == "Contrato social - partes (1)"


def test_separar_erro_de_pagina_vira_mensagem(pdf10):
    with pytest.raises(ConversionError, match="não existe"):
        engine.separar_pdf(pdf10, "11")
    assert not list(pdf10.parent.glob("*.tmp-*"))  # nada de lixo


def test_separar_recusa_nao_pdf(tmp_path):
    img = tmp_path / "foto.png"
    Image.new("RGB", (10, 10)).save(img)
    with pytest.raises(ConversionError, match="não é um PDF"):
        engine.separar_pdf(img, "1")


def test_separar_pdf_com_senha(tmp_path, pdf10):
    from pypdf import PdfWriter

    w = PdfWriter(clone_from=str(pdf10))
    w.encrypt("segredo")
    protegido = tmp_path / "protegido.pdf"
    with open(protegido, "wb") as f:
        w.write(f)
    with pytest.raises(ConversionError, match="senha"):
        engine.separar_pdf(protegido, "1")


# --- juntar -----------------------------------------------------------------

def test_juntar_pdfs_e_imagem_na_ordem(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["Alfa um", "Alfa dois"])
    b = make_pdf(tmp_path / "b.pdf", ["Beta um"])
    img = tmp_path / "foto.jpg"
    Image.new("RGB", (300, 200), (200, 30, 30)).save(img)
    hashes = [_hash(p) for p in (a, b, img)]
    r = engine.juntar_pdf([b, img, a], tmp_path / "junto.pdf")
    (saida,) = r.saidas
    t = _textos(saida)
    assert len(t) == 4
    assert "Beta um" in t[0] and "Alfa um" in t[2] and "Alfa dois" in t[3]
    assert [_hash(p) for p in (a, b, img)] == hashes


def test_juntar_nome_padrao_e_sem_sobrescrever(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A"])
    b = make_pdf(tmp_path / "b.pdf", ["B"])
    r1 = engine.juntar_pdf([a, b]).saidas[0]
    r2 = engine.juntar_pdf([a, b]).saidas[0]
    assert r1.name == "a + 1.pdf" and r2.name == "a + 1 (1).pdf"


def test_juntar_recusa_um_arquivo_e_formato_errado(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A"])
    with pytest.raises(ConversionError, match="pelo menos 2"):
        engine.juntar_pdf([a])
    txt = tmp_path / "n.txt"
    txt.write_text("oi", encoding="utf-8")
    with pytest.raises(ConversionError, match="não é PDF nem imagem"):
        engine.juntar_pdf([a, txt])


def test_juntar_nao_grava_por_cima_da_origem(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", ["A"])
    b = make_pdf(tmp_path / "b.pdf", ["B"])
    with pytest.raises(ConversionError, match="não pode ser um dos arquivos"):
        engine.juntar_pdf([a, b], a)


# --- botão direito e seleção múltipla ---------------------------------------

def test_menu_do_pdf_tem_separar_e_juntar():
    from conversor import shell

    entradas = {e.key: e.values for e in shell.build_entries(["C:/Lotus/Lotus.exe"])}
    raiz = next(k for k in entradas if k.endswith(r".pdf\shell\Lotus.Converter"))
    sep = entradas[raiz + r"\shell\96_separar\command"][""]
    jun = entradas[raiz + r"\shell\97_juntar"]
    assert '--menu-separar "%1"' in sep
    assert jun["MultiSelectModel"] == "Player"
    assert '--menu-juntar "%1"' in entradas[raiz + r"\shell\97_juntar\command"][""]
    # Planilha não entra em "Juntar" (só PDF e o que vira PDF por página).
    csv = next(k for k in entradas if k.endswith(r".csv\shell\Lotus.Converter"))
    assert not any(k.startswith(csv + r"\shell\97_juntar") for k in entradas)
    docx = next(k for k in entradas if k.endswith(r".docx\shell\Lotus.Converter"))
    assert not any(k.startswith(docx + r"\shell\97_juntar") for k in entradas)


def test_reunir_selecao_multipla(tmp_path):
    from conversor import agrupar

    pasta = tmp_path / "fila"
    # Os outros processos já anotaram seus arquivos (chegaram antes do dono dormir).
    pasta.mkdir()
    (pasta / "juntar.dono").touch()
    assert agrupar.reunir(str(tmp_path / "b.pdf"), pasta=pasta) is None  # não é o dono
    (pasta / "juntar.dono").unlink()
    relogio = iter(i * 0.1 for i in range(1000))
    lista = agrupar.reunir(str(tmp_path / "a.pdf"), pasta=pasta,
                           dormir=lambda _s: None, agora=lambda: next(relogio))
    assert [Path(p).name for p in lista] == ["b.pdf", "a.pdf"]
    assert not (pasta / "juntar.fila").exists() and not (pasta / "juntar.dono").exists()


def test_mover_ordem():
    from conversor.ui.janela_pdf import mover

    itens = ["a", "b", "c"]
    assert mover(itens, 2, -1) == 1 and itens == ["a", "c", "b"]
    assert mover(itens, 0, -1) == 0 and itens == ["a", "c", "b"]


def test_janelas_separar_e_juntar(tmp_path):
    import tkinter as tk

    from conversor.ui.janela_pdf import JanelaJuntar, JanelaSeparar

    pdf = make_pdf(tmp_path / "doc.pdf", ["Um", "Dois", "Tres"])
    outro = make_pdf(tmp_path / "outro.pdf", ["Quatro"])
    root = tk.Tk()
    try:
        s = JanelaSeparar(root, pdf)
        assert s.paginas.get() == "1-3"
        s.paginas.set("3, 1")
        s.modo.set(engine.SEPARAR_EXTRAIR)
        s.executar()
        while s.winfo_exists() and s.resultado is None and s.erro is None:
            root.update()
        assert "Tres" in _textos(s.resultado.saidas[0])[0]

        j = JanelaJuntar(root, [pdf, outro])
        j.lista.selection_clear(0, "end")
        j.lista.selection_set(1)
        j._mover(-1)
        assert [a.name for a in j.arquivos] == ["outro.pdf", "doc.pdf"]
        j.destino.set(str(tmp_path / "final.pdf"))
        j.executar()
        while j.winfo_exists() and j.resultado is None and j.erro is None:
            root.update()
        t = _textos(tmp_path / "final.pdf")
        assert len(t) == 4 and "Quatro" in t[0]
    finally:
        root.destroy()


def test_janela_escolher_mostra_acoes_de_pdf(tmp_path):
    import tkinter as tk
    from tkinter import ttk

    from conversor.menu import Chooser

    pdf = make_pdf(tmp_path / "a.pdf", ["A"])
    img = tmp_path / "b.png"
    Image.new("RGB", (20, 20)).save(img)

    def textos(paths):
        root = tk.Tk()
        try:
            c = Chooser(root, [str(p) for p in paths])
            pilha = list(c.winfo_children())
            achados = []
            while pilha:
                w = pilha.pop()
                pilha.extend(w.winfo_children())
                if isinstance(w, ttk.Button):
                    achados.append(w.cget("text"))
            return achados
        finally:
            root.destroy()

    assert "Separar PDF…" in textos([pdf]) and "Juntar em um PDF…" not in textos([pdf])
    assert "Juntar em um PDF…" in textos([pdf, img])
