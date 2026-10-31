"""Janelas abertas pelo botão direito e o lançador do Lotus.exe."""

from __future__ import annotations

import gc
import time

import pytest

tk = pytest.importorskip("tkinter")

from conversor import launcher, menu  # noqa: E402


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass
    gc.collect()  # coleta objetos do Tk aqui, na thread principal


def _wait(widget, cond, timeout=20):
    deadline = time.time() + timeout
    while not cond():
        widget.update()
        assert time.time() < deadline, "travou"
        time.sleep(0.05)


def test_convert_many_and_summary(sample, tmp_path):
    good = sample("png")
    bad = tmp_path / "x.png"
    bad.write_bytes(b"")
    outcomes = menu.convert_many([str(good), str(bad)], "jpg")
    failed, text = menu.summary(outcomes)
    assert failed
    assert "✓ amostra.png → amostra.jpg" in text
    assert "✗" in text and "vazio" in text and "lotus.log" in text


def test_chooser_shows_one_box_per_target(root, sample):
    ch = menu.Chooser(root, [str(sample("png"))])
    assert sorted(ch.buttons) == ["3mf", "avif", "bmp", "gif", "ico", "jpg", "pdf", "stl", "tiff", "webp"]


def test_chooser_intersects_multiple_files(root, sample):
    ch = menu.Chooser(root, [str(sample("png")), str(sample("csv"))])
    assert sorted(ch.buttons) == ["pdf"]  # imagem e planilha: só o PDF é comum
    ch = menu.Chooser(root, [str(sample("png")), str(sample("pptx"))])
    assert ch.buttons == {}  # sem PowerPoint, PPTX só vira TXT/MD


def test_chooser_converts_on_click(root, sample):
    src = sample("png")
    ch = menu.Chooser(root, [str(src)])
    ch.buttons["webp"].invoke()
    _wait(root, lambda: ch.worker and not ch.worker.is_alive() and str(ch.open_btn["state"]) == "normal")
    assert (src.parent / "amostra.webp").is_file()
    assert "✓" in ch.status["text"]


def test_quick_convert_success_shows_toast(root, sample, monkeypatch):
    src = sample("png")
    monkeypatch.setattr(root, "mainloop", lambda: None)
    assert menu.quick_convert([str(src)], "pdf", root=root) == 0
    assert (src.parent / "amostra.pdf").is_file()


def test_quick_convert_error_shows_dialog(root, tmp_path, monkeypatch):
    shown = {}
    monkeypatch.setattr(menu.messagebox, "showerror", lambda t, m, **k: shown.setdefault("m", m))
    bad = tmp_path / "v.png"
    bad.write_bytes(b"")
    assert menu.quick_convert([str(bad)], "jpg", root=root) == 1
    assert "vazio" in shown["m"]


def test_launcher_routes_menu_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(menu, "quick_convert", lambda paths, t: calls.append(("q", t, paths)) or 0)
    monkeypatch.setattr(menu, "choose", lambda paths: calls.append(("c", paths)) or 0)
    assert launcher.main(["--menu-converter", "pdf", "a.png", "b.png"]) == 0
    assert launcher.main(["--menu-escolher", "a.png"]) == 0
    assert calls == [("q", "pdf", ["a.png", "b.png"]), ("c", ["a.png"])]


def test_launcher_never_crashes_silently(monkeypatch):
    shown = []
    monkeypatch.setattr(launcher, "dispatch", lambda argv: 1 / 0)
    monkeypatch.setattr(launcher, "_show", lambda text, error=False: shown.append(text))
    assert launcher.main(["qualquer"]) == 1
    assert "Erro inesperado" in shown[0] and "lotus.log" in shown[0]


def test_launcher_bad_usage(monkeypatch):
    shown = []
    monkeypatch.setattr(launcher, "_show", lambda text, error=False: shown.append(text))
    assert launcher.main(["--menu-converter", "pdf"]) == 2
