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
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from conversor.core import registry, validate
from conversor.core.detect import DetectionError, detect, normalize_ext
from conversor.core.errors import explain
from conversor.logs import get_logger


LIMITE_CAMINHO = 200  # MAX_PATH é 260; a saída acrescenta pasta temporária e nome da página


def caminho_estendido(p: Path, plataforma: str | None = None) -> Path:
    """No Windows, caminhos longos ganham o prefixo \\\\?\\ (aceita até ~32 mil
    caracteres). Sem ele, gravar em pastas fundas (ex.: OneDrive) falha com
    "arquivo não encontrado" mesmo com o arquivo lá."""
    plataforma = plataforma or sys.platform
    s = str(p)
    if plataforma != "win32" or s.startswith("\\\\?\\") or len(s) < LIMITE_CAMINHO:
        return p
    s = os.path.abspath(s) if plataforma == sys.platform else s
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)


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


def _unique_dir(path: Path) -> Path:
    """Como _unique_path, mas para pastas (nome sem extensão)."""
    if not path.exists():
        return path
    n = 1
    while (cand := path.with_name(f"{path.name} ({n})")).exists():
        n += 1
    return cand


def _finish_multi(tmp_dir: Path, src: Path, target: str, out_dir: Path,
                  overwrite: bool, options: dict) -> Path:
    """Valida cada arquivo gerado e entrega um arquivo (1 saída) ou uma pasta (várias)."""
    files = sorted(p for p in tmp_dir.iterdir() if p.is_file())
    if not files:
        raise ConversionError("A conversão não gerou nenhum arquivo.")
    for f in files:
        problem = validate.check(f, target)
        if problem:
            raise ConversionError(f"Saída inválida ({f.name}): {problem}")
    if len(files) == 1:
        final = out_dir / f"{src.stem}.{target}"
        if not overwrite:
            final = _unique_path(final)
        return _place(files[0], final, overwrite, options)
    # Pasta nunca é sobrescrita: apagar uma pasta inteira do usuário é arriscado demais.
    final_dir = _unique_dir(out_dir / f"{src.stem} - páginas {target.upper()}")
    os.replace(tmp_dir, final_dir)
    return final_dir


def convert_file(
    src: Path | str,
    target: str,
    out_dir: Path | str | None = None,
    overwrite: bool = False,
    options: dict | None = None,
) -> Result:
    src = caminho_estendido(Path(src))
    target = normalize_ext(target)
    options = dict(options or {})

    try:
        detection = detect(src)
    except DetectionError as e:
        raise ConversionError(str(e)) from e

    warnings = [detection.warning] if detection.warning else []
    source_fmt = detection.fmt
    options["_source_format"] = source_fmt
    options["_target"] = target

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

    out_dir = caminho_estendido(Path(out_dir) if out_dir else src.parent)
    final = out_dir / f"{src.stem}.{target}"
    if final.resolve() == src.resolve():
        raise ConversionError("A saída coincide com o arquivo de origem.")

    log = get_logger()
    # O temporário mantém a extensão de destino porque algumas ferramentas
    # (ex.: ffmpeg) escolhem o formato pela extensão.
    sufixo = "" if conv.multi else f".{target}"
    tmp = out_dir / f"{src.stem}.tmp-{uuid.uuid4().hex[:8]}{sufixo}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if conv.multi:
            tmp.mkdir()
            conv.fn(src, tmp, options)
            final = _finish_multi(tmp, src, target, out_dir, overwrite, options)
        else:
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
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp.exists():
            tmp.unlink()

    warnings.extend(options.get("_warnings", []))
    return Result(src, final, source_fmt, target, warnings)


# ---------------------------------------------------------------------------
# Separar e juntar PDFs (operações de página; mesma gravação segura acima)

SEPARAR_INTERVALOS = "intervalos"  # um PDF por intervalo
SEPARAR_EXTRAIR = "extrair"        # um PDF só com as páginas escolhidas


@dataclass
class ResultadoPaginas:
    saidas: list[Path]
    avisos: list[str] = field(default_factory=list)


def _validar_pdf(caminho: Path) -> None:
    problema = validate.check(caminho, "pdf")
    if problema:
        raise ConversionError(f"PDF gerado inválido ({caminho.name}): {problema}")


def _como_conversao(fn):
    """Mesmo tratamento de erro do convert_file: mensagem clara, detalhe no log."""
    from conversor.core.errors import ConversaoPaginasErro

    def envolvida(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ConversionError:
            raise
        except ConversaoPaginasErro as e:
            raise ConversionError(str(e)) from e
        except Exception as e:
            get_logger().exception("%s falhou", fn.__name__)
            origem = args[0] if args and isinstance(args[0], Path) else None
            raise ConversionError(explain(e, origem)) from e
    envolvida.__name__ = fn.__name__
    envolvida.__doc__ = fn.__doc__
    return envolvida


def _exigir_pdf(src: Path) -> None:
    try:
        fmt = detect(src).fmt
    except DetectionError as e:
        raise ConversionError(str(e)) from e
    if fmt != "pdf":
        raise ConversionError(f"{src.name} não é um PDF (é {fmt.upper()}).")


@_como_conversao
def separar_pdf(src: Path | str, paginas: str, modo: str = SEPARAR_INTERVALOS,
                out_dir: Path | str | None = None) -> ResultadoPaginas:
    """Separa `src` sem alterá-lo. modo=intervalos: um PDF por intervalo, numa
    pasta "<nome> - partes"; modo=extrair: um PDF "<nome> (p2,5-7).pdf"."""
    from conversor.converters import pdf_paginas as pp

    src = caminho_estendido(Path(src))
    _exigir_pdf(src)
    intervalos = pp.interpretar_paginas(paginas, pp.total_paginas(src))
    out_dir = caminho_estendido(Path(out_dir) if out_dir else src.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    avisos: list[str] = []
    tmp = out_dir / f"{src.stem}.tmp-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    try:
        if modo == SEPARAR_EXTRAIR:
            nome = ",".join(pp.rotulo(i)[1:] for i in intervalos)
            arq = tmp / f"{src.stem} (p{nome}).pdf"
            pp.gravar_paginas(src, intervalos, arq, avisos)
            _validar_pdf(arq)
            final = _unique_path(out_dir / arq.name)
            os.replace(arq, final)
            return ResultadoPaginas([final], _sem_repetidos(avisos))
        if modo != SEPARAR_INTERVALOS:
            raise ConversionError(f"Modo de separação desconhecido: {modo}.")
        for intervalo in intervalos:
            arq = tmp / f"{src.stem} ({pp.rotulo(intervalo)}).pdf"
            if arq.exists():  # intervalo repetido: um arquivo só
                continue
            pp.gravar_paginas(src, [intervalo], arq, avisos)
            _validar_pdf(arq)
        pasta = _unique_dir(out_dir / f"{src.stem} - partes")
        os.replace(tmp, pasta)
        ordem = {f"{src.stem} ({pp.rotulo(i)}).pdf": n for n, i in enumerate(intervalos)}
        saidas = sorted(pasta.iterdir(), key=lambda p: ordem.get(p.name, 0))
        return ResultadoPaginas(saidas, _sem_repetidos(avisos))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


@_como_conversao
def juntar_pdf(arquivos: list[Path | str], destino: Path | str | None = None) -> ResultadoPaginas:
    """Junta PDFs e imagens, NA ORDEM DADA, num PDF novo. Originais intactos."""
    from conversor.converters import pdf_paginas as pp
    from conversor.converters.images import IMAGES

    caminhos = [caminho_estendido(Path(a)) for a in arquivos]
    if len(caminhos) < 2:
        raise ConversionError("Escolha pelo menos 2 arquivos para juntar.")
    itens: list[tuple[Path, str]] = []
    for c in caminhos:
        try:
            fmt = detect(c).fmt
        except DetectionError as e:
            raise ConversionError(str(e)) from e
        if fmt != "pdf" and fmt not in IMAGES + ["heic", "avif"]:
            raise ConversionError(f"{c.name} não é PDF nem imagem ({fmt.upper()}); não dá para juntar.")
        itens.append((c, fmt))
    if destino is None:
        destino = caminhos[0].parent / f"{caminhos[0].stem} + {len(caminhos) - 1}.pdf"
    destino = caminho_estendido(Path(destino))
    if destino.suffix.lower() != ".pdf":
        destino = destino.with_name(destino.name + ".pdf")
    if any(destino.resolve() == c.resolve() for c in caminhos):
        raise ConversionError("O PDF de saída não pode ser um dos arquivos que estão sendo juntados.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    avisos: list[str] = []
    tmp = destino.with_name(f"{destino.stem}.tmp-{uuid.uuid4().hex[:8]}.pdf")
    try:
        pp.juntar(itens, tmp, avisos)
        _validar_pdf(tmp)
        final = _unique_path(destino)
        os.replace(tmp, final)
        return ResultadoPaginas([final], _sem_repetidos(avisos))
    finally:
        if tmp.exists():
            tmp.unlink()


def _sem_repetidos(itens: list[str]) -> list[str]:
    return list(dict.fromkeys(itens))
