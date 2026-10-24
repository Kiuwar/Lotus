"""DOCX → TXT/MD/HTML e PPTX → TXT/MD sem Word nem PowerPoint (Windows e Mac).

DOCX e PPTX são pacotes ZIP com XML (Office Open XML, ECMA-376). Lemos o XML
com defusedxml (proteção contra XML malicioso; arquivo vem do usuário) e
mantemos a ESTRUTURA: títulos, parágrafos, negrito/itálico, links, listas
(numeradas ou com marcadores), tabelas e, no PPTX, o texto e as notas de cada
slide. Fontes, cores, imagens e posições NÃO são mantidas: o usuário é avisado
(regra 7). Para conversão fiel (PDF, DOC, RTF…) existem as conversões pelo
Word/PowerPoint (office.py).
"""

from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree as ET

from conversor.core.engine import ConversionError
from conversor.core.registry import register

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


@dataclass
class Trecho:
    texto: str
    negrito: bool = False
    italico: bool = False
    link: str | None = None


@dataclass
class Bloco:
    tipo: str                      # "titulo" | "par" | "item" | "tabela" | "nota" | "codigo"
    trechos: list[Trecho] = field(default_factory=list)
    nivel: int = 0                 # título: 1–6; item: recuo (0, 1, …)
    ordenado: bool = False
    linhas: list[list[str]] = field(default_factory=list)
    cabecalho: bool = False        # tabela: a 1ª linha é cabeçalho (<th> no HTML)

    def texto(self) -> str:
        return "".join(t.texto for t in self.trechos)


# ---------- leitura comum ----------

def _xml(z: zipfile.ZipFile, nome: str):
    try:
        return ET.fromstring(z.read(nome))
    except KeyError:
        return None


def _rels(z: zipfile.ZipFile, parte: str) -> dict[str, tuple[str, str]]:
    """{rId: (alvo, modo)} das relações de uma parte do pacote."""
    pasta, arquivo = posixpath.split(parte)
    raiz = _xml(z, posixpath.join(pasta, "_rels", arquivo + ".rels"))
    if raiz is None:
        return {}
    return {r.get("Id"): (r.get("Target", ""), r.get("TargetMode", "")) for r in raiz.iter(REL + "Relationship")}


def _ligado(el, tag: str) -> bool:
    """Propriedade booleana do Word (<w:b/>, <w:b w:val="0"/>…)."""
    x = el.find(tag) if el is not None else None
    return x is not None and x.get(W + "val", "true").lower() not in ("0", "false", "off")


def _abrir(src: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(src)
    except zipfile.BadZipFile as e:
        raise ConversionError(f"{src.name} está corrompido (não é um pacote ZIP válido).") from e


# ---------- DOCX ----------

def _estilos(z) -> dict[str, str]:
    raiz = _xml(z, "word/styles.xml")
    if raiz is None:
        return {}
    saida = {}
    for st in raiz.iter(W + "style"):
        nome = st.find(W + "name")
        if nome is not None:
            saida[st.get(W + "styleId", "")] = nome.get(W + "val", "").lower()
    return saida


def _numeracao(z) -> dict[str, dict[str, str]]:
    """{numId: {ilvl: numFmt}} — para saber se a lista é numerada."""
    raiz = _xml(z, "word/numbering.xml")
    if raiz is None:
        return {}
    abstratos = {}
    for ab in raiz.iter(W + "abstractNum"):
        niveis = {}
        for lvl in ab.iter(W + "lvl"):
            fmt = lvl.find(W + "numFmt")
            niveis[lvl.get(W + "ilvl", "0")] = fmt.get(W + "val", "bullet") if fmt is not None else "bullet"
        abstratos[ab.get(W + "abstractNumId")] = niveis
    saida = {}
    for num in raiz.iter(W + "num"):
        ab = num.find(W + "abstractNumId")
        if ab is not None:
            saida[num.get(W + "numId")] = abstratos.get(ab.get(W + "val"), {})
    return saida


def _trechos_docx(p, links: dict) -> list[Trecho]:
    trechos: list[Trecho] = []

    def run(r, link=None):
        rpr = r.find(W + "rPr")
        partes = []
        for c in r:
            if c.tag == W + "t":
                partes.append(c.text or "")
            elif c.tag == W + "tab":
                partes.append("\t")
            elif c.tag in (W + "br", W + "cr"):
                partes.append("\n")
            elif c.tag == W + "noBreakHyphen":
                partes.append("-")
        if partes:
            trechos.append(Trecho("".join(partes), _ligado(rpr, W + "b"), _ligado(rpr, W + "i"), link))

    def percorrer(el, link=None):
        for c in el:
            if c.tag == W + "r":
                run(c, link)
            elif c.tag == W + "hyperlink":
                alvo = links.get(c.get(R + "id"), ("", ""))[0] or (
                    "#" + c.get(W + "anchor") if c.get(W + "anchor") else None)
                percorrer(c, alvo)
            elif c.tag in (W + "ins", W + "smartTag", W + "fldSimple", W + "customXml", W + "sdt",
                           W + "sdtContent"):
                percorrer(c, link)
            # w:del (texto apagado com controle de alterações) fica de fora
    percorrer(p)
    return trechos


def ler_docx(src: Path) -> tuple[list[Bloco], list[str]]:
    with _abrir(src) as z:
        doc = _xml(z, "word/document.xml")
        if doc is None:
            raise ConversionError(f"{src.name}: falta word/document.xml (não é um DOCX válido).")
        estilos, numeracao = _estilos(z), _numeracao(z)
        links = _rels(z, "word/document.xml")
        extras = [n for n in z.namelist()
                  if re.fullmatch(r"word/(header\d*|footer\d*|footnotes|endnotes)\.xml", n)
                  and "".join(ET.fromstring(z.read(n)).itertext()).strip()]
    corpo = doc.find(W + "body")
    blocos: list[Bloco] = []

    def paragrafo(p):
        ppr = p.find(W + "pPr")
        trechos = _trechos_docx(p, links)
        estilo = ""
        nivel_titulo = 0
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            if ps is not None:
                estilo = estilos.get(ps.get(W + "val", ""), ps.get(W + "val", "").lower())
            ol = ppr.find(W + "outlineLvl")
            if ol is not None and ol.get(W + "val", "9").isdigit() and int(ol.get(W + "val")) < 6:
                nivel_titulo = int(ol.get(W + "val")) + 1
        m = re.fullmatch(r"heading (\d)", estilo)
        if m:
            nivel_titulo = min(6, int(m.group(1)))
        elif estilo == "title":
            nivel_titulo = 1
        num = ppr.find(W + "numPr") if ppr is not None else None
        if nivel_titulo:
            blocos.append(Bloco("titulo", trechos, nivel=nivel_titulo))
        elif num is not None and num.find(W + "numId") is not None \
                and num.find(W + "numId").get(W + "val") != "0":
            ilvl_el = num.find(W + "ilvl")
            ilvl = ilvl_el.get(W + "val", "0") if ilvl_el is not None else "0"
            fmt = numeracao.get(num.find(W + "numId").get(W + "val"), {}).get(ilvl, "bullet")
            blocos.append(Bloco("item", trechos, nivel=int(ilvl) if ilvl.isdigit() else 0,
                                ordenado=fmt not in ("bullet", "none")))
        else:
            blocos.append(Bloco("par", trechos))

    def tabela(t):
        linhas = []
        for tr in t.iter(W + "tr"):
            linhas.append([" ".join("".join(x.text or "" for x in p.iter(W + "t")) for p in tc.iter(W + "p")).strip()
                           for tc in tr.findall(W + "tc")])
        blocos.append(Bloco("tabela", linhas=linhas))

    def percorrer(el):
        for c in el:
            if c.tag == W + "p":
                paragrafo(c)
            elif c.tag == W + "tbl":
                tabela(c)
            elif c.tag in (W + "sdt", W + "sdtContent", W + "customXml"):
                percorrer(c)
    if corpo is not None:
        percorrer(corpo)

    imagens = sum(1 for el in doc.iter() if el.tag in (W + "drawing", W + "pict"))
    avisos = ["Só o conteúdo foi mantido (títulos, texto, listas, tabelas e links); fontes, cores "
              "e layout do Word não."]
    if imagens:
        avisos.append(f"{imagens} imagem(ns) do documento não foram incluídas.")
    if extras:
        avisos.append("Cabeçalho, rodapé e notas de rodapé não foram incluídos.")
    return blocos, avisos


# ---------- PPTX ----------

def _texto_paragrafo(p) -> tuple[str, int]:
    partes = []
    for c in p:
        if c.tag in (A + "r", A + "fld"):
            t = c.find(A + "t")
            partes.append(t.text or "" if t is not None else "")
        elif c.tag == A + "br":
            partes.append("\n")
    ppr = p.find(A + "pPr")
    nivel = int(ppr.get("lvl", "0")) if ppr is not None and ppr.get("lvl", "0").isdigit() else 0
    return "".join(partes), nivel


def _tipo_ph(sp) -> str | None:
    ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    return None if ph is None else ph.get("type", "body")


def ler_pptx(src: Path) -> tuple[list[Bloco], list[str]]:
    blocos: list[Bloco] = []
    imagens = 0
    with _abrir(src) as z:
        pres = _xml(z, "ppt/presentation.xml")
        if pres is None:
            raise ConversionError(f"{src.name}: falta ppt/presentation.xml (não é um PPTX válido).")
        rels = _rels(z, "ppt/presentation.xml")
        ids = [s.get(R + "id") for s in pres.iter(P + "sldId")]
        for n, rid in enumerate(ids, start=1):
            alvo = rels.get(rid, ("", ""))[0]
            parte = posixpath.normpath(posixpath.join("ppt", alvo))
            slide = _xml(z, parte)
            if slide is None:
                continue
            titulo, corpo, tabelas = "", [], []
            for sp in slide.iter(P + "sp"):
                tipo = _tipo_ph(sp)
                paras = [_texto_paragrafo(p) for p in sp.iter(A + "p")]
                paras = [(t, nv) for t, nv in paras if t.strip()]
                if tipo in ("title", "ctrTitle") and not titulo:
                    titulo = " ".join(t for t, _ in paras)
                elif tipo not in ("sldNum", "dt", "ftr"):
                    corpo.extend(paras)
            for tbl in slide.iter(A + "tbl"):
                tabelas.append([["".join(t.text or "" for t in tc.iter(A + "t")).strip() for tc in tr.iter(A + "tc")]
                                for tr in tbl.iter(A + "tr")])
            imagens += sum(1 for _ in slide.iter(P + "pic"))
            oculto = slide.get("show") == "0"
            rotulo = f"Slide {n}" + (": " + titulo if titulo else "") + (" (oculto)" if oculto else "")
            blocos.append(Bloco("titulo", [Trecho(rotulo)], nivel=2))
            for t, nv in corpo:
                blocos.append(Bloco("item", [Trecho(t)], nivel=nv))
            for linhas in tabelas:
                blocos.append(Bloco("tabela", linhas=linhas))
            # Notas do apresentador
            for rid_n, (alvo_n, _modo) in _rels(z, parte).items():
                if "notesSlide" in alvo_n:
                    notas = _xml(z, posixpath.normpath(posixpath.join(posixpath.dirname(parte), alvo_n)))
                    if notas is not None:
                        texto = "\n".join(t for sp in notas.iter(P + "sp") if _tipo_ph(sp) == "body"
                                          for t, _ in (_texto_paragrafo(p) for p in sp.iter(A + "p")) if t.strip())
                        if texto:
                            blocos.append(Bloco("nota", [Trecho(texto)]))
    avisos = ["Só o texto foi mantido (títulos, tópicos, tabelas e notas de cada slide); imagens, "
              "cores e posições dos slides não."]
    if imagens:
        avisos.append(f"{imagens} imagem(ns) dos slides não foram incluídas.")
    if not ids:
        avisos.append("A apresentação não tem slides.")
    return blocos, avisos


# ---------- escrita ----------

def para_txt(blocos: list[Bloco]) -> str:
    linhas: list[str] = []
    contadores: dict[int, int] = {}
    for b in blocos:
        if b.tipo != "item":
            contadores.clear()
        if b.tipo == "titulo":
            if linhas:
                linhas.append("")
            linhas.append(b.texto())
            linhas.append("")
        elif b.tipo == "par":
            linhas.append(b.texto())
        elif b.tipo == "item":
            contadores[b.nivel] = contadores.get(b.nivel, 0) + 1
            for k in [k for k in contadores if k > b.nivel]:
                del contadores[k]
            marca = f"{contadores[b.nivel]}." if b.ordenado else "•"
            linhas.append("  " * b.nivel + f"{marca} {b.texto()}")
        elif b.tipo == "tabela":
            linhas.extend("\t".join(c) for c in b.linhas)
            linhas.append("")
        elif b.tipo == "nota":
            linhas.append("Notas: " + b.texto())
        elif b.tipo == "codigo":
            linhas.extend(["", b.texto(), ""])
    return "\n".join(linhas).strip() + "\n"


_MD_ESCAPE = re.compile(r"([\\`*_\[\]#|<>])")


def _md_trecho(t: Trecho) -> str:
    texto = _MD_ESCAPE.sub(r"\\\1", t.texto).replace("\n", "  \n")
    nucleo = texto.strip()
    if not nucleo:
        return texto
    ini, fim = texto[: len(texto) - len(texto.lstrip())], texto[len(texto.rstrip()):]
    if t.negrito and t.italico:
        nucleo = f"***{nucleo}***"
    elif t.negrito:
        nucleo = f"**{nucleo}**"
    elif t.italico:
        nucleo = f"*{nucleo}*"
    if t.link:
        nucleo = f"[{nucleo}]({t.link.replace(' ', '%20').replace(')', '%29')})"
    return ini + nucleo + fim


def para_md(blocos: list[Bloco]) -> str:
    saida: list[str] = []
    anterior = None
    ordenado_antes: bool | None = None
    for b in blocos:
        conteudo = "".join(_md_trecho(t) for t in b.trechos)
        if b.tipo != "item":
            ordenado_antes = None
        if b.tipo == "item":
            if anterior != "item" or (b.nivel == 0 and ordenado_antes is not None
                                      and ordenado_antes != b.ordenado):
                saida.append("")  # lista nova (ou troca de numerada ↔ marcadores)
            saida.append("    " * b.nivel + ("1. " if b.ordenado else "- ") + conteudo)
            ordenado_antes = b.ordenado if b.nivel == 0 else ordenado_antes
        else:
            saida.append("")
            if b.tipo == "titulo":
                saida.append("#" * b.nivel + " " + conteudo)
            elif b.tipo == "par":
                if conteudo.strip():
                    saida.append(conteudo)
            elif b.tipo == "nota":
                saida.append("> **Notas:** " + conteudo.replace("\n", "\n> "))
            elif b.tipo == "codigo":
                cerca = "````" if "```" in b.texto() else "```"
                saida.extend([cerca, b.texto(), cerca])
            elif b.tipo == "tabela" and b.linhas:
                largura = max(len(r) for r in b.linhas)
                linhas = [r + [""] * (largura - len(r)) for r in b.linhas]
                cel = lambda c: _MD_ESCAPE.sub(r"\\\1", c).replace("\n", " ")  # noqa: E731
                saida.append("| " + " | ".join(cel(c) for c in linhas[0]) + " |")
                saida.append("|" + "---|" * largura)
                saida.extend("| " + " | ".join(cel(c) for c in r) + " |" for r in linhas[1:])
        anterior = b.tipo
    return re.sub(r"\n{3,}", "\n\n", "\n".join(saida)).strip() + "\n"


def _html_trecho(t: Trecho) -> str:
    s = html.escape(t.texto).replace("\n", "<br>")
    if t.negrito:
        s = f"<strong>{s}</strong>"
    if t.italico:
        s = f"<em>{s}</em>"
    if t.link:
        s = f'<a href="{html.escape(t.link, quote=True)}">{s}</a>'
    return s


def para_html(blocos: list[Bloco], titulo: str) -> str:
    corpo: list[str] = []
    pilha: list[tuple[int, str]] = []  # listas abertas: (nível, "ul"|"ol")

    def fechar_ate(nivel: int):
        while pilha and pilha[-1][0] >= nivel:
            corpo.append(f"</{pilha.pop()[1]}>")

    for b in blocos:
        conteudo = "".join(_html_trecho(t) for t in b.trechos)
        if b.tipo == "item":
            tag = "ol" if b.ordenado else "ul"
            fechar_ate(b.nivel + 1)
            if not pilha or pilha[-1][0] < b.nivel or pilha[-1][1] != tag:
                if pilha and pilha[-1][0] == b.nivel:
                    corpo.append(f"</{pilha.pop()[1]}>")
                corpo.append(f"<{tag}>")
                pilha.append((b.nivel, tag))
            corpo.append(f"<li>{conteudo}</li>")
            continue
        fechar_ate(0)
        if b.tipo == "titulo":
            corpo.append(f"<h{b.nivel}>{conteudo}</h{b.nivel}>")
        elif b.tipo == "par":
            corpo.append(f"<p>{conteudo}</p>" if conteudo.strip() else "")
        elif b.tipo == "nota":
            corpo.append(f"<blockquote><strong>Notas:</strong> {conteudo}</blockquote>")
        elif b.tipo == "codigo":
            corpo.append(f"<pre><code>{html.escape(b.texto())}</code></pre>")
        elif b.tipo == "tabela":
            linhas = "".join(
                "<tr>" + "".join(f"<{t}>{html.escape(c)}</{t}>" for c in r) + "</tr>"
                for i, r in enumerate(b.linhas) for t in ["th" if b.cabecalho and i == 0 else "td"])
            corpo.append(f"<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\">{linhas}</table>")
    fechar_ate(0)
    return ("<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{html.escape(titulo)}</title>\n</head>\n<body>\n"
            + "\n".join(c for c in corpo if c) + "\n</body>\n</html>\n")


NOTA_DOCX = "Texto, títulos, listas, tabelas e links (sem Word); fontes, cores e imagens não."
NOTA_PPTX = "Texto e notas de cada slide (sem PowerPoint); imagens e layout não."


@register(["docx"], ["txt", "md", "html"], category="Documento", notes=NOTA_DOCX)
def docx_para_texto(src: Path, dst: Path, options: dict) -> None:
    blocos, avisos = ler_docx(src)
    _gravar(src, dst, blocos, avisos, options)


@register(["pptx"], ["txt", "md"], category="Apresentação", notes=NOTA_PPTX)
def pptx_para_texto(src: Path, dst: Path, options: dict) -> None:
    blocos, avisos = ler_pptx(src)
    _gravar(src, dst, blocos, avisos, options)


def _gravar(src: Path, dst: Path, blocos: list[Bloco], avisos: list[str], options: dict) -> None:
    alvo = dst.suffix.lstrip(".")
    if alvo == "txt":
        texto = para_txt(blocos)
    elif alvo == "md":
        texto = para_md(blocos)
    else:
        texto = para_html(blocos, src.stem)
    if not any(b.texto().strip() or b.linhas for b in blocos):
        avisos = avisos + [f"{src.name} não tem texto (só imagens ou está vazio)."]
    dst.write_text(texto, encoding="utf-8")
    options.setdefault("_warnings", []).extend(avisos)
