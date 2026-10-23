"""Motor de conversão: detecta, converte, valida e só então grava.

Garantias:
- O arquivo de origem nunca é modificado.
- Nada é sobrescrito sem `overwrite=True`; senão o nome ganha " (1)", " (2)"...
- A saída é escrita num arquivo temporário e validada (reaberta) antes de
  receber o nome final. Se a validação falhar, o temporário é apagado e o
  erro é reportado: o usuário nunca recebe um arquivo corrompido em silêncio.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from conversor.core import registry, validate
from conversor.core.detect import DetectionError, detect, normalize_ext
from conversor.core.errors import explain
from conversor.logs import get_logger


class ConversionError(Exception):
    pass


@dataclass
class Result:
    source: Path
    output: Path
    source_format: str
    target_format: str
    warnings: list[str] = field(default_factory=list)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _place(tmp: Path, final: Path, overwrite: bool, options: dict) -> Path:
    """Dá o nome final ao temporário.

    Reparo automático: se o destino existente está bloqueado (aberto no Excel,
    num visualizador etc.), não perdemos a conversão: salvamos com um nome
    novo e avisamos.
    """
    try:
        os.replace(tmp, final)
        return final
    except PermissionError:
        if not (overwrite and final.exists()):
            raise
    alt = _unique_path(final)
    os.replace(tmp, alt)
    options.setdefault("_warnings", []).append(
        f"{final.name} está em uso por outro programa; salvo como {alt.name}."
    )
    return alt


def convert_file(
    src: Path | str,
    target: str,
    out_dir: Path | str | None = None,
    overwrite: bool = False,
    options: dict | None = None,
) -> Result:
    src = Path(src)
    target = normalize_ext(target)
    options = dict(options or {})

    try:
        detection = detect(src)
    except DetectionError as e:
        raise ConversionError(str(e)) from e

    warnings = [detection.warning] if detection.warning else []
    source_fmt = detection.fmt
    options["_source_format"] = source_fmt

    if source_fmt == target:
        raise ConversionError(f"{src.name} já está no formato {target.upper()}.")

    conv = registry.find(source_fmt, target)
    if conv is None:
        options_list = registry.targets_for(source_fmt, only_available=False)
        hint = ", ".join(o.upper() for o in options_list) or "nenhum"
        raise ConversionError(
            f"Conversão {source_fmt.upper()} -> {target.upper()} não suportada. "
            f"Destinos possíveis para {source_fmt.upper()}: {hint}."
        )
    if not conv.available():
        raise ConversionError(
            f"Conversão {source_fmt.upper()} -> {target.upper()} requer um componente "
            f"ausente. {conv.notes}"
        )

    out_dir = Path(out_dir) if out_dir else src.parent
    final = out_dir / f"{src.stem}.{target}"
    if final.resolve() == src.resolve():
        raise ConversionError("A saída coincide com o arquivo de origem.")

    log = get_logger()
    # O temporário mantém a extensão de destino porque algumas ferramentas
    # (ex.: ffmpeg) escolhem o formato pela extensão.
    tmp = out_dir / f"{src.stem}.tmp-{uuid.uuid4().hex[:8]}.{target}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if not overwrite:
            final = _unique_path(final)
        conv.fn(src, tmp, options)
        problem = validate.check(tmp, target)
        if problem:
            raise ConversionError(f"Saída inválida ({target.upper()}): {problem}")
        final = _place(tmp, final, overwrite, options)
    except ConversionError as e:
        log.warning("%s -> %s: %s", src, target, e)
        raise
    except Exception as e:  # erro de biblioteca/sistema: mensagem clara ao usuário, detalhe no log
        log.exception("%s -> %s falhou", src, target)
        raise ConversionError(explain(e, src)) from e
    finally:
        if tmp.exists():
            tmp.unlink()

    warnings.extend(options.get("_warnings", []))
    return Result(src, final, source_fmt, target, warnings)
