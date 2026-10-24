"""Menu do botão direito: montagem das chaves, instalação, remoção e reparo."""

from __future__ import annotations

import sys

import pytest

from conversor import diagnostics, shell

from .fake_winreg import FakeWinreg

LAUNCHER = [r"C:\Program Files\Lotus\Lotus.exe"]


def _entries():
    return shell.build_entries(LAUNCHER)


def _by_key(entries):
    return {e.key: e.values for e in entries}


def test_png_menu_has_all_targets_and_chooser():
    keys = _by_key(_entries())
    root = rf"Software\Classes\SystemFileAssociations\.png\shell\{shell.VERB}"
    assert keys[root] == {
        "MUIVerb": "Converter para",
        "SubCommands": "",
        "Icon": r"C:\Program Files\Lotus\Lotus.exe,0",
    }
    subs = [k for k in keys if k.startswith(root + "\\shell\\") and not k.endswith("command")]
    labels = [keys[k]["MUIVerb"] for k in subs]
    assert labels == ["AVIF", "BMP", "GIF", "ICO", "JPG", "PDF", "TIFF", "WEBP", "Escolher formato…"]
    cmd = keys[root + r"\shell\15_pdf\command"][""]
    assert cmd == r'"C:\Program Files\Lotus\Lotus.exe" --menu-converter pdf "%1"'
    assert keys[root + r"\shell\99_escolher\command"][""].endswith('--menu-escolher "%1"')


def test_aliases_get_menu_too():
    keys = _by_key(_entries())
    for ext in ("jpeg", "tif", "markdown"):
        assert rf"Software\Classes\SystemFileAssociations\.{ext}\shell\{shell.VERB}" in keys


def test_every_registered_source_has_menu():
    from conversor.core import registry

    roots = shell.menu_roots(_entries())
    for src in {c.source for c in registry.all_converters()}:
        assert any(rf"\.{src}\shell" in r for r in roots), src


def test_menu_only_offers_registered_conversions():
    """Nenhum item do menu pode prometer conversão inexistente."""
    from conversor.core import registry

    for key, values in _by_key(_entries()).items():
        cmd = values.get("", "")
        if "--menu-converter" in cmd:
            ext = key.split("SystemFileAssociations\\.")[1].split("\\")[0]
            target = cmd.split("--menu-converter ")[1].split(" ")[0]
            src = shell.source_extensions()[ext]
            assert registry.find(src, target) is not None, (src, target)


def test_install_inspect_uninstall_roundtrip():
    wr = FakeWinreg()
    wr.CreateKeyEx(wr.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\.png\shell\OutroApp")
    n = shell.install(_entries(), wr)
    assert n == len(shell.source_extensions())
    assert shell.inspect(_entries(), wr) == []
    assert shell.uninstall(wr) == n
    assert len(shell.inspect(_entries(), wr)) == len(_entries())
    # o menu de outro programa não pode ser apagado
    assert r"software\classes\systemfileassociations\.png\shell\outroapp" in wr.keys


def test_repair_fixes_moved_executable(monkeypatch):
    wr = FakeWinreg()
    monkeypatch.setattr(shell, "launcher_command", lambda: [r"D:\velho\Lotus.exe"])
    shell.install(winreg_module=wr)
    monkeypatch.setattr(shell, "launcher_command", lambda: [r"E:\novo\Lotus.exe"])

    installed, problems = diagnostics.menu_state(wr)
    assert installed and problems
    msg = diagnostics.repair_menu(wr)
    assert "reparado" in msg
    assert diagnostics.menu_state(wr) == (True, [])
    assert not any("velho" in v for vals in wr.keys.values() for v in vals.values())


def test_repair_does_not_install_unasked():
    wr = FakeWinreg()
    assert "não instalado" in diagnostics.repair_menu(wr)
    assert wr.keys == {}


def test_diagnostics_report_lines():
    report = diagnostics.run(FakeWinreg())
    assert any(line.startswith("ffmpeg:") for line in report)
    assert any(line.startswith("Pasta de log:") for line in report)


@pytest.mark.skipif(sys.platform != "win32", reason="registro real só no Windows")
def test_real_registry_roundtrip():
    import winreg

    prefix = "Software\\LotusTeste\\"  # fora de Software\Classes: o Explorer não enxerga
    try:
        n = shell.install(_entries(), winreg, root_prefix=prefix)
        assert n > 0
        assert shell.inspect(_entries(), winreg, root_prefix=prefix) == []
        assert shell.uninstall(winreg, root_prefix=prefix) == n
    finally:
        shell._delete_tree(winreg, winreg.HKEY_CURRENT_USER, "Software\\LotusTeste")
