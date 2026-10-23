from __future__ import annotations

from conversor.cli import main


def test_cli_converts_and_reports(sample, tmp_path, capsys):
    src = sample("png")
    code = main([str(src), "--para", "jpg", "--saida", str(tmp_path / "o"), "--qualidade", "80"])
    assert code == 0
    assert (tmp_path / "o" / "amostra.jpg").is_file()
    assert "OK" in capsys.readouterr().out


def test_cli_returns_error_code_on_failure(tmp_path, capsys):
    assert main([str(tmp_path / "nao_existe.png"), "--para", "jpg"]) == 1
    assert "não encontrado" in capsys.readouterr().err


def test_cli_rejects_bad_quality(sample):
    assert main([str(sample("png")), "--para", "jpg", "--qualidade", "0"]) == 2


def test_cli_lists(capsys):
    assert main(["--listar"]) == 0
    assert "png -> jpg" in capsys.readouterr().out
