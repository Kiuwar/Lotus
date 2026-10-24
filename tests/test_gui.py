"""Teste da interface: precisa de um display (no Linux, rode com xvfb-run)."""

from __future__ import annotations

import gc
import time

import pytest

tk = pytest.importorskip("tkinter")

from conversor.gui import App, common_targets  # noqa: E402


def test_common_targets_is_intersection():
    assert common_targets(["png", "csv"]) == ["pdf"], "imagem e planilha: ambos viram PDF"
    assert common_targets(["png", "pptx"]) == []
    assert "pdf" in common_targets(["png", "jpg"])
    assert "png" not in common_targets(["png"])


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    root.withdraw()
    a = App(root)
    yield a
    root.destroy()
    del a, root
    gc.collect()  # coleta objetos do Tk aqui, na thread principal


def test_gui_converts_end_to_end(app, sample, tmp_path):
    src = sample("png")
    bad = tmp_path / "ruim.xyz"
    bad.write_bytes(b"\x00\x01")
    app.add_files([str(src), str(bad), str(src)])  # duplicado é ignorado

    assert len(app.files) == 2
    assert "JPG" in app.target_box["values"]
    app.target.set("JPG")
    app.start()

    deadline = time.time() + 20
    while app.worker.is_alive() or not app.events.empty():
        app.update()
        assert time.time() < deadline, "conversão travou"
        time.sleep(0.05)
    app.update()

    assert (src.parent / "amostra.jpg").is_file()
    assert str(app.convert_btn["state"]) == "normal"
    log = app.log.get("1.0", "end")
    assert "OK" in log


# ---------- cenário das fotos do usuário (PDF na lista) ----------

def test_situation_and_reason_texts(sample, tmp_path):
    from conversor.gui import motivo_sem_destino, situacao_arquivo

    assert situacao_arquivo("pdf") == "pronto"
    assert situacao_arquivo("zip") == "sem conversão para ZIP"
    # DOCX converte para TXT/MD/HTML mesmo sem Word; o .doc antigo precisa do Word.
    assert situacao_arquivo("docx") == "pronto"
    assert situacao_arquivo("doc").startswith("indisponível: requer o microsoft word")
    assert motivo_sem_destino(["pdf"]) is None
    assert "não têm um formato de destino em comum" in motivo_sem_destino(["pdf", "xlsx"])
    assert "ZIP" in motivo_sem_destino(["zip"])


def test_pdf_now_offers_formats_and_converts(app, sample):
    src = sample("pdf")
    app.add_files([str(src)])
    valores = list(app.target_box["values"])
    assert {"PNG", "JPG", "TXT"} <= set(valores), valores
    assert app.tree.set(next(iter(app.files)), "status") == "pronto"
    assert app.hint["text"] == ""

    app.target.set("TXT")
    app.start()
    deadline = time.time() + 20
    while app.worker.is_alive() or not app.events.empty():
        app.update()
        assert time.time() < deadline
        time.sleep(0.05)
    app.update()
    assert "ação e coração" in (src.parent / "amostra.txt").read_text(encoding="utf-8")


def test_specific_message_instead_of_generic(app, sample, tmp_path, monkeypatch):
    import zipfile

    from conversor import gui

    z = tmp_path / "pacote.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("a.txt", "x")
    app.add_files([str(z)])
    assert "ZIP" in app.hint["text"]
    mostrado = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda t, m: mostrado.append(m))
    app.start()
    assert mostrado and "ZIP" in mostrado[0]
    assert "Adicione arquivos válidos" not in mostrado[0]
