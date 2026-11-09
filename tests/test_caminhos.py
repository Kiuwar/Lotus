"""Erro "não foi encontrado" ao converter PDF → JPG no Windows (relato real, 0.10.0).

A mensagem culpava o PDF de origem por QUALQUER FileNotFoundError, inclusive o
de gravar a saída num caminho longo demais (MAX_PATH). Aqui: a mensagem diz o
que de fato falhou e caminhos longos ganham o prefixo \\\\?\\ no Windows.
"""

from pathlib import Path

from conversor.core import engine
from conversor.core.errors import explain


def test_caminho_curto_nao_muda():
    p = Path("C:/curto/a.pdf")
    assert engine.caminho_estendido(p, "win32") == p


def test_caminho_longo_ganha_prefixo_no_windows():
    longo = "C:\\Users\\Patricia\\OneDrive\\" + "pasta\\" * 40 + "a.pdf"
    r = engine.caminho_estendido(Path(longo), "win32")
    assert str(r).startswith("\\\\?\\")


def test_rede_usa_unc():
    longo = "\\\\servidor\\share\\" + "pasta\\" * 40 + "a.pdf"
    assert str(engine.caminho_estendido(Path(longo), "win32")).startswith("\\\\?\\UNC\\servidor")


def test_fora_do_windows_nao_muda():
    longo = Path("/home/" + "pasta/" * 60 + "a.pdf")
    assert engine.caminho_estendido(longo, "linux") == longo


def test_saida_nao_encontrada_nao_culpa_a_origem(tmp_path):
    src = tmp_path / "X Administrativo OK.pdf"
    src.write_bytes(b"%PDF-1.4")
    e = FileNotFoundError(2, "No such file", str(tmp_path / "x.tmp-1" / "pagina_001.jpg"))
    msg = explain(e, src)
    assert "não foi encontrado" not in msg
    assert "gravar a saída" in msg and "Como resolver" in msg


def test_origem_existente_mas_ilegivel_explica(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4")
    msg = explain(FileNotFoundError(2, "x", str(src)), src)
    assert "embora ele exista" in msg and "Como resolver" in msg


def test_origem_apagada_mantem_mensagem(tmp_path):
    src = tmp_path / "sumiu.pdf"
    assert "não foi encontrado" in explain(FileNotFoundError(2, "x", str(src)), src)


def test_pdf_para_jpg_com_nome_com_espacos(tmp_path):
    from tests.conftest import make_pdf

    alvo = make_pdf(tmp_path / "X Administrativo OK.pdf", ["um", "dois"])
    r = engine.convert_file(alvo, "jpg")
    jpgs = sorted(r.output.glob("*.jpg"))
    assert len(jpgs) == 2
    from PIL import Image
    with Image.open(jpgs[0]) as im:
        assert im.format == "JPEG" and im.width > 500
