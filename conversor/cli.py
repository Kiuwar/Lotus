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
    p.add_argument("--espessura", type=float,
                   help="impressão 3D, em mm: espessura da peça (SVG → STL, padrão 2) ou máxima da litofania (padrão 3)")
    p.add_argument("--largura", type=float, help="impressão 3D, em mm: largura final da peça (litofania: padrão 100)")
    p.add_argument("--modo", choices=["litofania", "relevo"],
                   help="imagem → STL: litofania (escuro = grosso, padrão) ou relevo (claro = alto)")
    p.add_argument("--separar", metavar="PAGINAS",
                   help='PDF: um PDF por intervalo (ex.: "1-3, 4-9, 10-")')
    p.add_argument("--extrair", metavar="PAGINAS",
                   help='PDF: um PDF só com estas páginas, nesta ordem (ex.: "2, 5-7")')
    p.add_argument("--juntar", metavar="SAIDA.pdf", nargs="?", const="",
                   help="junta os arquivos (PDF e imagens), na ordem dada, num PDF")
    p.add_argument("--listar", action="store_true", help="lista as conversões disponíveis")
    p.add_argument("--instalar-menu", action="store_true", help="instala o menu do botão direito (Windows)")
    p.add_argument("--remover-menu", action="store_true", help="remove o menu do botão direito (Windows)")
    p.add_argument("--reparar", action="store_true", help="diagnostica e repara a instalação")
    p.add_argument("--diagnostico-mac", action="store_true",
                   help="mostra por que o painel por atalho não abre no Mac (não altera nada)")
    p.add_argument("--versao", action="version", version=f"%(prog)s {__version__}")
    return p


def _paginas(args) -> int:
    from conversor.core import engine

    if not args.arquivos:
        print("Informe o(s) arquivo(s).", file=sys.stderr)
        return 2
    try:
        if args.juntar is not None:
            r = engine.juntar_pdf(args.arquivos, args.juntar or None)
        else:
            if len(args.arquivos) != 1:
                print("Separar/extrair: informe um PDF por vez.", file=sys.stderr)
                return 2
            modo = engine.SEPARAR_EXTRAIR if args.extrair is not None else engine.SEPARAR_INTERVALOS
            r = engine.separar_pdf(args.arquivos[0], args.extrair if args.extrair is not None
                                   else args.separar, modo, args.out_dir)
    except ConversionError as e:
        print(f"ERRO  {e}", file=sys.stderr)
        return 1
    for aviso in r.avisos:
        print(f"AVISO {aviso}")
    for saida in r.saidas:
        print(f"OK    {saida}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # No Windows, saída redirecionada usa cp1252: nomes de arquivo com
    # caracteres fora dela não podem derrubar o programa.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)

    if args.listar:
        for c in registry.all_converters():
            # O motivo vem do próprio conversor (ffmpeg, Word, PowerPoint…).
            flag = "" if c.available() else f"  (indisponível: {c.notes or 'componente ausente'})"
            print(f"{c.category:10} {c.source:>5} -> {c.target}{flag}")
        return 0

    if args.separar is not None or args.extrair is not None or args.juntar is not None:
        return _paginas(args)

    if args.diagnostico_mac:
        if sys.platform != "darwin":
            print("O diagnóstico do painel é do Mac. No Windows, use --reparar.", file=sys.stderr)
            return 2
        from conversor.atalho import diagnostico_mac

        print(diagnostico_mac.executar())
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
    for nome in ("espessura", "largura"):
        valor = getattr(args, nome)
        if valor is not None:
            if valor <= 0:
                print(f"--{nome} deve ser maior que zero (em mm).", file=sys.stderr)
                return 2
            options[nome] = valor
    if args.modo:
        options["modo"] = args.modo

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
