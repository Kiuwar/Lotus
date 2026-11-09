"""Separar e juntar PDFs (pypdf, local).

Não é uma conversão "formato → formato" do registro: são operações sobre
páginas. A gravação segura (temporário, validação, nome único) fica em
`core/engine.py` (`separar_pdf`, `juntar_pdf`).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from conversor.core.errors import ConversaoPaginasErro

Intervalo = tuple[int, int]  # páginas base 1, inclusivo


def interpretar_paginas(texto: str, total: int) -> list[Intervalo]:
    """'1-3, 5; 8-' → [(1, 3), (5, 5), (8, total)]. Erros em português."""
    partes = [p.strip() for p in re.split(r"[,;]", texto or "") if p.strip()]
    if not partes:
        raise ConversaoPaginasErro(
            "Nenhuma página informada. Como resolver: digite, por exemplo, 1-3, 5 ou 8-.")
    saida: list[Intervalo] = []
    for parte in partes:
        m = re.fullmatch(r"(\d+)\s*(?:-\s*(\d*))?", parte)
        if not m:
            raise ConversaoPaginasErro(
                f"\"{parte}\" não é uma página nem um intervalo. "
                "Como resolver: use números e hífen, como 1-3, 5 ou 8-.")
        ini = int(m.group(1))
        fim = ini if m.group(2) is None else (int(m.group(2)) if m.group(2) else total)
        for n in (ini, fim):
            if n < 1 or n > total:
                raise ConversaoPaginasErro(
                    f"A página {n} não existe: o PDF tem {total} página{'s' if total != 1 else ''}.")
        if fim < ini:
            raise ConversaoPaginasErro(
                f"Intervalo invertido: {parte}. Como resolver: escreva {fim}-{ini}.")
        saida.append((ini, fim))
    return saida


def rotulo(intervalo: Intervalo) -> str:
    ini, fim = intervalo
    return f"p{ini}" if ini == fim else f"p{ini}-{fim}"


def _ler(src: Path):
    from pypdf import PdfReader

    from conversor.converters.pdf import SENHA

    leitor = PdfReader(str(src))
    if leitor.is_encrypted:
        try:
            ok = leitor.decrypt("")  # PDF só com senha de "dono" abre sem senha
        except Exception:
            ok = 0
        if not ok:
            raise ConversaoPaginasErro(SENHA.format(nome=src.name))
    return leitor


def total_paginas(src: Path) -> int:
    return len(_ler(src).pages)


def _avisos_perdas(leitor, avisos: list[str]) -> None:
    try:
        if leitor.outline:
            avisos.append("Os marcadores (sumário lateral) do PDF original não foram copiados.")
    except Exception:
        pass
    try:
        if leitor.get_fields():
            avisos.append("Campos de formulário podem não funcionar nas partes separadas.")
    except Exception:
        pass


def gravar_paginas(src: Path, intervalos: list[Intervalo], dst: Path, avisos: list[str]) -> None:
    """Grava num único PDF as páginas dos intervalos, na ordem dada."""
    from pypdf import PdfWriter

    leitor = _ler(src)
    _avisos_perdas(leitor, avisos)
    escritor = PdfWriter()
    for ini, fim in intervalos:
        for i in range(ini - 1, fim):
            escritor.add_page(leitor.pages[i])  # mantém rotação e tamanho da página
    with open(dst, "wb") as f:
        escritor.write(f)


def juntar(arquivos: list[tuple[Path, str]], dst: Path, avisos: list[str]) -> None:
    """arquivos: (caminho, formato detectado). PDF entra inteiro; imagem vira página."""
    from pypdf import PdfWriter

    from conversor.converters.images import image_to_pdf

    escritor = PdfWriter()
    with tempfile.TemporaryDirectory(prefix="lotus-juntar-") as tmp:
        for n, (caminho, fmt) in enumerate(arquivos):
            if fmt == "pdf":
                leitor = _ler(caminho)
                for pagina in leitor.pages:
                    escritor.add_page(pagina)
            else:
                pagina_pdf = Path(tmp) / f"{n}.pdf"
                opcoes: dict = {}
                image_to_pdf(caminho, pagina_pdf, opcoes)
                avisos.extend(opcoes.get("_warnings", []))
                for pagina in _ler(pagina_pdf).pages:
                    escritor.add_page(pagina)
        with open(dst, "wb") as f:
            escritor.write(f)
