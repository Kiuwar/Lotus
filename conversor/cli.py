"""Linha de comando: python -m conversor ARQUIVOS --para FORMATO."""

from __future__ import annotations

import argparse
import sys

from conversor import __version__
from conversor.core import registry
from conversor.core.engine import ConversionError, convert_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="conversor", description="Converte arquivos (offline).")
    p.add_argument("arquivos", nargs="*", help="arquivos de origem")
    p.add_argument("--para", dest="target", help="formato de destino (ex.: pdf, jpg, xlsx)")
    p.add_argument("--saida", dest="out_dir", help="pasta de saída (padrão: mesma da origem)")
    p.add_argument("--sobrescrever", action="store_true", help="sobrescreve arquivo existente")
    p.add_argument("--qualidade", type=int, help="qualidade JPG/WEBP (1-100, padrão 90)")
    p.add_argument("--separador", help="separador do CSV gerado (padrão ;)")
    p.add_argument("--listar", action="store_true", help="lista as conversões disponíveis")
    p.add_argument("--instalar-menu", action="store_true", help="instala o menu do botão direito (Windows)")
    p.add_argument("--remover-menu", action="store_true", help="remove o menu do botão direito (Windows)")
    p.add_argument("--reparar", action="store_true", help="diagnostica e repara a instalação")
    p.add_argument("--versao", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    # No Windows, saída redirecionada usa cp1252: nomes de arquivo com
    # caracteres fora dela não podem derrubar o programa.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)

    if args.listar:
        for c in registry.all_converters():
            flag = "" if c.available() else "  (indisponível: requer ffmpeg)"
            print(f"{c.category:10} {c.source:>5} -> {c.target}{flag}")
        return 0

    if args.reparar:
        from conversor import diagnostics

        for line in diagnostics.run():
            print(line)
        return 0

    if args.instalar_menu or args.remover_menu:
        if sys.platform != "win32":
            print("O menu do botão direito só existe no Windows.", file=sys.stderr)
            return 2
        from conversor import shell

        if args.remover_menu:
            print(f"Menu removido de {shell.uninstall()} tipos de arquivo.")
        else:
            print(f"Menu instalado em {shell.install()} tipos de arquivo.")
        return 0

    if not args.arquivos or not args.target:
        build_parser().print_usage(sys.stderr)
        print("Informe arquivos e --para FORMATO (ou use --listar).", file=sys.stderr)
        return 2

    options: dict = {}
    if args.qualidade is not None:
        if not 1 <= args.qualidade <= 100:
            print("--qualidade deve estar entre 1 e 100.", file=sys.stderr)
            return 2
        options["quality"] = args.qualidade
    if args.separador:
        options["csv_delimiter_out"] = args.separador

    failures = 0
    for path in args.arquivos:
        try:
            r = convert_file(path, args.target, args.out_dir, args.sobrescrever, dict(options))
        except ConversionError as e:
            failures += 1
            print(f"ERRO  {e}", file=sys.stderr)
            continue
        print(f"OK    {r.source.name} -> {r.output}")
        for w in r.warnings:
            print(f"AVISO {w}")
    return 1 if failures else 0
