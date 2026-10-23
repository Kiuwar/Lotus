"""Teste da interface: precisa de um display (no Linux, rode com xvfb-run)."""

from __future__ import annotations

import time

import pytest

tk = pytest.importorskip("tkinter")

from conversor.gui import App, common_targets  # noqa: E402


def test_common_targets_is_intersection():
    both = common_targets(["png", "csv"])
    assert both == []
    assert "pdf" in common_targets(["png", "jpg"])
    assert "png" not in common_targets(["png"])


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("sem display disponível")
    root.withdraw()
    a = App(root)
    yield a
    root.destroy()


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
