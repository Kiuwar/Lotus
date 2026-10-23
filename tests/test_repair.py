"""Reparação de erros: recuperação automática e mensagens com solução."""

from __future__ import annotations

import errno
import os

import pytest
from PIL import Image, ImageFile

from conversor.core import engine
from conversor.core.engine import ConversionError, convert_file
from conversor.core.errors import explain
from conversor.logs import log_file


def _truncated_jpeg(path):
    Image.effect_noise((200, 200), 64).convert("RGB").save(path, quality=95)
    data = path.read_bytes()
    path.write_bytes(data[: int(len(data) * 0.6)])  # corta 40% do final
    with pytest.raises(OSError, match="truncated"):  # garante que está danificado mesmo
        with Image.open(path) as im:
            im.load()


def test_truncated_image_is_recovered_with_warning(tmp_path):
    src = tmp_path / "incompleta.jpg"
    _truncated_jpeg(src)
    res = convert_file(src, "png", out_dir=tmp_path / "o")
    with Image.open(res.output) as im:
        assert im.size == (200, 200)
    assert any("danificado" in w for w in res.warnings)
    assert ImageFile.LOAD_TRUNCATED_IMAGES is False, "flag global do Pillow precisa ser restaurada"


def test_garbage_image_is_not_repaired(tmp_path):
    src = tmp_path / "lixo.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"lixo" * 10)
    with pytest.raises(ConversionError):
        convert_file(src, "jpg", out_dir=tmp_path)


def test_locked_destination_falls_back_to_new_name(sample, tmp_path, monkeypatch):
    src = sample("png")
    first = convert_file(src, "jpg", out_dir=tmp_path).output

    real_replace = os.replace

    def locked(a, b):  # simula o arquivo aberto em outro programa (Windows)
        if str(b) == str(first):
            raise PermissionError(13, "Acesso negado", str(b))
        return real_replace(a, b)

    monkeypatch.setattr(engine.os, "replace", locked)
    res = convert_file(src, "jpg", out_dir=tmp_path, overwrite=True)
    assert res.output.name == "amostra (1).jpg"
    assert any("em uso" in w for w in res.warnings)


def test_permission_error_without_overwrite_explains_fix(sample, tmp_path, monkeypatch):
    def denied(a, b):
        raise PermissionError(13, "Acesso negado", str(b))

    monkeypatch.setattr(engine.os, "replace", denied)
    with pytest.raises(ConversionError, match="Como resolver: feche o arquivo"):
        convert_file(sample("png"), "jpg", out_dir=tmp_path)
    assert not [p for p in tmp_path.iterdir() if ".tmp-" in p.name]


def test_disk_full_message():
    assert "Disco cheio" in explain(OSError(errno.ENOSPC, "No space left on device"))


def test_unknown_error_keeps_original_message():
    assert "boom" in explain(ValueError("boom"))


def test_failures_are_logged_locally(tmp_path):
    src = tmp_path / "ruim.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 20)
    with pytest.raises(ConversionError):
        convert_file(src, "jpg", out_dir=tmp_path)
    assert "ruim.png" in log_file().read_text(encoding="utf-8")
