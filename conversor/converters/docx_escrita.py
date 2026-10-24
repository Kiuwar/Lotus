"""TXT, Markdown e HTML → DOCX; Markdown/HTML → PDF; DOCX → PDF simples. Sem Word.

O DOCX é escrito à mão seguindo o Office Open XML (ECMA-376, parte 1): pacote
ZIP com [Content_Types].xml, relações, document.xml, styles.xml e
numbering.xml. Mantém a ESTRUTURA (títulos com os estilos "Título 1…6" do
Word, parágrafos, negrito/itálico, links, listas numeradas e com marcadores,
tabelas e blocos de código). CSS, imagens e scripts do HTML não entram: o
usuário é avisado (regra 7).

O PDF sem Word é desenhado pelo fpdf2 (`write_html`) a partir dos mesmos
blocos: serve para ler e imprimir, não reproduz o layout do Word.

Links: só http(s) e mailto viram link clicável (um "javascript:" ou caminho
local num HTML baixado não deve virar link no documento).
"""

from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from conversor.converters.documents import _FONT_CANDIDATES, _read_text
from conversor.converters.office_texto import Bloco, Trecho, ler_docx, para_html, para_md, para_txt
from conversor.core.engine import ConversionError
from conversor.core.registry import register

LINK_SEGURO = re.compile(r"(?i)^(https?://|mailto:)")
# Caracteres que o XML 1.0 não aceita (o Word recusaria abrir o arquivo).
_XML_INVALIDO = re.compile("[^\x09\x0a\x0d\x20-퟿-�\U00010000-\U0010ffff]")


def _avisar(options: dict, texto: str) -> None:
    avisos = options.setdefault("_warnings", [])
    if texto not in avisos:
        avisos.append(texto)


# ---------- leitura: TXT, HTML e Markdown viram blocos ----------

def ler_txt(texto: str) -> list[Bloco]:
    """Cada linha vira um parágrafo; linhas em branco são mantidas."""
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if linhas and linhas[-1] == "":
        linhas.pop()
    return [Bloco("par", [Trecho(linha)] if linha else []) for linha in linhas]


class _LeitorHTML(HTMLParser):
    _BLOCO = {"p", "div", "li", "blockquote", "pre", "section", "article", "header", "footer",
              "main", "aside", "nav", "figure", "figcaption", "address", "dt", "dd", "hr"}
    _IGNORAR = {"script", "style", "head", "title", "template", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocos: list[Bloco] = []
        self.trechos: list[Trecho] = []
        self.negrito = self.italico = self.ignorando = self.pre = 0
        self.titulo = 0
        self.links: list[str | None] = []
        self.listas: list[bool] = []          # pilha: True = numerada
        self.tabelas = 0
        self.linhas: list[list[str]] = []
        self.linha: list[str] | None = None
        self.celula: list[str] | None = None
        self.cabecalho = False
        self.imagens = 0

    # -- texto acumulado no bloco atual --
    def _fechar_bloco(self) -> None:
        trechos, self.trechos = self.trechos, []
        if self.pre:
            texto = "".join(t.texto for t in trechos).strip("\n")
            if texto:
                self.blocos.append(Bloco("codigo", [Trecho(texto)]))
            return
        limpos: list[Trecho] = []
        for t in trechos:
            if t.texto == "\n":
                limpos.append(t)
                continue
            texto = re.sub(r"\s+", " ", t.texto)
            if limpos and limpos[-1].texto != "\n" and limpos[-1].texto.endswith(" "):
                texto = texto.lstrip(" ")
            elif not limpos or limpos[-1].texto == "\n":
                texto = texto.lstrip(" ")
            if texto:
                limpos.append(Trecho(texto, t.negrito, t.italico, t.link))
        while limpos and limpos[-1].texto in ("\n", " "):
            limpos.pop()
        if limpos:
            limpos[-1] = Trecho(limpos[-1].texto.rstrip(" "), limpos[-1].negrito,
                                limpos[-1].italico, limpos[-1].link)
        if not any(t.texto.strip() for t in limpos):
            return
        if self.titulo:
            self.blocos.append(Bloco("titulo", limpos, nivel=self.titulo))
        elif self.listas:
            self.blocos.append(Bloco("item", limpos, nivel=len(self.listas) - 1,
                                     ordenado=self.listas[-1]))
        else:
            self.blocos.append(Bloco("par", limpos))

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORAR:
            self.ignorando += 1
            return
        if self.ignorando:
            return
        a = dict(attrs)
        if self.tabelas:
            if tag == "table":
                self.tabelas += 1
            elif tag == "tr" and self.tabelas == 1:
                self.linha = []
            elif tag in ("td", "th") and self.linha is not None:
                self.celula = []
                self.cabecalho = self.cabecalho or (tag == "th" and not self.linhas)
            elif tag == "br" and self.celula is not None:
                self.celula.append(" ")
            elif tag == "img":
                self.imagens += 1
            return
        if tag == "table":
            self._fechar_bloco()
            self.tabelas, self.linhas, self.cabecalho = 1, [], False
        elif re.fullmatch(r"h[1-6]", tag):
            self._fechar_bloco()
            self.titulo = int(tag[1])
        elif tag in ("ul", "ol"):
            self._fechar_bloco()
            self.listas.append(tag == "ol")
        elif tag in self._BLOCO:
            self._fechar_bloco()
            if tag == "pre":
                self.pre += 1
        elif tag == "br":
            self.trechos.append(Trecho("\n"))
        elif tag in ("b", "strong"):
            self.negrito += 1
        elif tag in ("i", "em"):
            self.italico += 1
        elif tag == "a":
            href = (a.get("href") or "").strip()
            self.links.append(href if LINK_SEGURO.match(href) else None)
        elif tag == "img":
            self.imagens += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ("br", "img", "hr"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self._IGNORAR:
            self.ignorando = max(0, self.ignorando - 1)
            return
        if self.ignorando:
            return
        if self.tabelas:
            if tag == "table":
                self.tabelas -= 1
                if not self.tabelas and self.linhas:
                    largura = max(len(l) for l in self.linhas)
                    linhas = [l + [""] * (largura - len(l)) for l in self.linhas]
                    self.blocos.append(Bloco("tabela", linhas=linhas, cabecalho=self.cabecalho))
            elif tag in ("td", "th") and self.celula is not None and self.linha is not None:
                self.linha.append(re.sub(r"\s+", " ", "".join(self.celula)).strip())
                self.celula = None
            elif tag == "tr" and self.tabelas == 1 and self.linha is not None:
                if self.linha:
                    self.linhas.append(self.linha)
                self.linha = None
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._fechar_bloco()
            self.titulo = 0
        elif tag in ("ul", "ol"):
            self._fechar_bloco()
            if self.listas:
                self.listas.pop()
        elif tag in self._BLOCO:
            self._fechar_bloco()
            if tag == "pre":
                self.pre = max(0, self.pre - 1)
        elif tag in ("b", "strong"):
            self.negrito = max(0, self.negrito - 1)
        elif tag in ("i", "em"):
            self.italico = max(0, self.italico - 1)
        elif tag == "a" and self.links:
            self.links.pop()

    def handle_data(self, data):
        if self.ignorando:
            return
        if self.tabelas:
            if self.celula is not None:
                self.celula.append(data)
            return
        link = next((l for l in reversed(self.links) if l), None) if self.links else None
        self.trechos.append(Trecho(data, bool(self.negrito), bool(self.italico), link))

    def close(self):
        super().close()
        self._fechar_bloco()


def ler_html(texto: str) -> tuple[list[Bloco], int]:
    """Blocos do HTML e quantas imagens ficaram de fora."""
    leitor = _LeitorHTML()
    leitor.feed(texto)
    leitor.close()
    return leitor.blocos, leitor.imagens


def ler_md(texto: str) -> tuple[list[Bloco], int]:
    import markdown

    return ler_html(markdown.markdown(texto, extensions=["tables", "fenced_code"]))


def _blocos_da_origem(src: Path, options: dict) -> list[Bloco]:
    origem = src.suffix.lower().lstrip(".")
    texto = _read_text(src, options)
    if origem == "txt":
        return ler_txt(texto)
    blocos, imagens = ler_md(texto) if origem in ("md", "markdown") else ler_html(texto)
    if origem in ("html", "htm"):
        _avisar(options, "Só o conteúdo do HTML foi mantido (títulos, texto, listas, tabelas e "
                         "links); estilos (CSS), scripts e layout da página não.")
    if imagens:
        _avisar(options, f"{imagens} imagem(ns) não foram incluídas.")
    return blocos


# ---------- escrita do DOCX ----------

_TIPOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\
<Default Extension="xml" ContentType="application/xml"/>\
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>\
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>\
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>\
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>\
</Types>"""

_RELS_PACOTE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>\
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>\
</Relationships>"""

_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">\
<Application>Lotus</Application></Properties>"""

_NS_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_NS_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

# Tamanhos em meio-ponto (sz=22 → 11 pt), espaços em vinte avos de ponto.
_TAM_TITULO = {1: 32, 2: 28, 3: 26, 4: 24, 5: 22, 6: 22}


def _estilos_xml() -> str:
    titulos = "".join(
        f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
        '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
        f'<w:pPr><w:keepNext/><w:spacing w:before="{240 if n < 3 else 160}" w:after="80"/>'
        f'<w:outlineLvl w:val="{n - 1}"/></w:pPr>'
        f'<w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="{_TAM_TITULO[n]}"/></w:rPr></w:style>'
        for n in range(1, 7))
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles {_NS_W}>'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" '
        'w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/>'
        '<w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr>'
        '</w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
        + titulos +
        '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
        '<w:basedOn w:val="Normal"/><w:uiPriority w:val="34"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="40"/><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Codigo"><w:name w:val="Código"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/><w:spacing w:after="120" w:line="240" '
        'w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" '
        'w:cs="Courier New"/><w:sz w:val="20"/></w:rPr></w:style>'
        '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
        '<w:uiPriority w:val="99"/><w:unhideWhenUsed/><w:rPr><w:color w:val="0563C1"/>'
        '<w:u w:val="single"/></w:rPr></w:style>'
        '<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/>'
        '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/>'
        '<w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
        '</w:tblCellMar></w:tblPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
        '<w:basedOn w:val="TableNormal"/><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
        '<w:tblPr><w:tblBorders>'
        + "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                  for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
        + '</w:tblBorders></w:tblPr></w:style></w:styles>'
    )


def _numeracao_xml(listas_numeradas: int) -> str:
    marcadores = ["•", "◦", "▪"]

    def nivel(i: int, numerada: bool) -> str:
        if numerada:
            fmt, texto = "decimal", f"%{i + 1}."
        else:
            fmt, texto = "bullet", marcadores[i % 3]
        return (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
                f'<w:lvlText w:val="{texto}"/><w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{720 * (i + 1)}" w:hanging="360"/></w:pPr></w:lvl>')

    abstratos = "".join(
        f'<w:abstractNum w:abstractNumId="{a}"><w:multiLevelType w:val="hybridMultilevel"/>'
        + "".join(nivel(i, a == 1) for i in range(9)) + "</w:abstractNum>"
        for a in (0, 1))
    # numId 1: marcadores (compartilhado). numId 2…: cada lista numerada recomeça em 1.
    nums = '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>' + "".join(
        f'<w:num w:numId="{2 + k}"><w:abstractNumId w:val="1"/>'
        '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'
        for k in range(listas_numeradas))
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:numbering {_NS_W}>{abstratos}{nums}</w:numbering>'


class _Escritor:
    def __init__(self) -> None:
        self.links: dict[str, str] = {}     # url → rId
        self.removidos = 0

    def limpar(self, texto: str) -> str:
        limpo, n = _XML_INVALIDO.subn("", texto)
        self.removidos += n
        return limpo

    def _rid(self, url: str) -> str:
        if url not in self.links:
            self.links[url] = f"rId{10 + len(self.links)}"
        return self.links[url]

    def corrida(self, t: Trecho, estilo_link: bool = True) -> str:
        props = ""
        if t.link and estilo_link:
            props += '<w:rStyle w:val="Hyperlink"/>'
        if t.negrito:
            props += "<w:b/>"
        if t.italico:
            props += "<w:i/>"
        partes = []
        for pedaco in re.split(r"(\t|\n)", self.limpar(t.texto)):
            if pedaco == "\t":
                partes.append("<w:tab/>")
            elif pedaco == "\n":
                partes.append("<w:br/>")
            elif pedaco:
                partes.append(f'<w:t xml:space="preserve">{escape(pedaco)}</w:t>')
        if not partes:
            return ""
        r = f"<w:r>{f'<w:rPr>{props}</w:rPr>' if props else ''}{''.join(partes)}</w:r>"
        if t.link:
            return f'<w:hyperlink r:id="{self._rid(t.link)}" w:history="1">{r}</w:hyperlink>'
        return r

    def paragrafo(self, trechos: list[Trecho], ppr: str = "") -> str:
        corpo = "".join(self.corrida(t) for t in trechos)
        return f"<w:p>{f'<w:pPr>{ppr}</w:pPr>' if ppr else ''}{corpo}</w:p>"

    def tabela(self, b: Bloco) -> str:
        colunas = max((len(l) for l in b.linhas), default=1)
        largura = 9000 // colunas  # ~15,9 cm úteis em A4 com margens de 2,5 cm
        grade = "".join(f'<w:gridCol w:w="{largura}"/>' for _ in range(colunas))
        linhas = []
        for i, linha in enumerate(b.linhas):
            negrito = b.cabecalho and i == 0
            cel = "".join(
                f'<w:tc><w:tcPr><w:tcW w:w="{largura}" w:type="dxa"/></w:tcPr>'
                f"{self.paragrafo([Trecho(texto, negrito=negrito)])}</w:tc>"
                for texto in linha + [""] * (colunas - len(linha)))
            cab = "<w:trPr><w:tblHeader/></w:trPr>" if negrito else ""
            linhas.append(f"<w:tr>{cab}{cel}</w:tr>")
        return ('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/>'
                '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" '
                f'w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>{grade}</w:tblGrid>{"".join(linhas)}</w:tbl>')


def escrever_docx(blocos: list[Bloco], dst: Path, titulo: str) -> int:
    """Grava o DOCX. Devolve quantos caracteres inválidos para XML foram removidos."""
    e = _Escritor()
    corpo: list[str] = []
    listas_numeradas = 0
    num_atual: int | None = None
    anterior_item = False
    for b in blocos:
        if b.tipo == "item":
            if b.ordenado:
                if not anterior_item or num_atual is None:
                    listas_numeradas += 1
                    num_atual = 1 + listas_numeradas
                num = num_atual
            else:
                num = 1
            anterior_item = True
            ppr = (f'<w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="{min(b.nivel, 8)}"/>'
                   f'<w:numId w:val="{num}"/></w:numPr>')
            corpo.append(e.paragrafo(b.trechos, ppr))
            continue
        anterior_item, num_atual = False, None
        if b.tipo == "titulo":
            corpo.append(e.paragrafo(b.trechos, f'<w:pStyle w:val="Heading{min(max(b.nivel, 1), 6)}"/>'))
        elif b.tipo == "codigo":
            corpo.append(e.paragrafo(b.trechos, '<w:pStyle w:val="Codigo"/>'))
        elif b.tipo == "tabela":
            corpo.append(e.tabela(b))
        else:
            corpo.append(e.paragrafo(b.trechos))
    if not corpo or corpo[-1].startswith("<w:tbl>"):
        corpo.append("<w:p/>")  # o Word espera um parágrafo depois de uma tabela final
    secao = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" '
             'w:bottom="1417" w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {_NS_W} {_NS_R}>'
                 f'<w:body>{"".join(corpo)}{secao}</w:body></w:document>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/numbering" Target="numbering.xml"/>'
            + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/'
                      f'2006/relationships/hyperlink" Target={quoteattr(url)} TargetMode="External"/>'
                      for url, rid in e.links.items())
            + "</Relationships>")
    nucleo = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
              'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
              f"<dc:title>{escape(e.limpar(titulo))}</dc:title></cp:coreProperties>")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TIPOS)
        z.writestr("_rels/.rels", _RELS_PACOTE)
        z.writestr("docProps/core.xml", nucleo)
        z.writestr("docProps/app.xml", _APP)
        z.writestr("word/document.xml", documento)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/styles.xml", _estilos_xml())
        z.writestr("word/numbering.xml", _numeracao_xml(listas_numeradas))
    return e.removidos


# ---------- PDF simples a partir dos blocos (fpdf2) ----------

# Variantes (negrito, itálico) das fontes de documents._FONT_CANDIDATES.
_VARIANTES = {
    "arial.ttf": ("arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "segoeui.ttf": ("segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    "DejaVuSans.ttf": ("DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
    "Arial.ttf": ("Arial Bold.ttf", "Arial Italic.ttf", "Arial Bold Italic.ttf"),
}


def _estilos_pdf() -> dict:
    """Títulos em azul-escuro e negrito (como no DOCX), listas com mais espaço.
    O padrão do fpdf2 é título vermelho."""
    from fpdf.fonts import TextStyle

    tamanhos = {1: 20, 2: 16, 3: 14, 4: 12, 5: 11, 6: 11}
    estilos = {f"h{n}": TextStyle(font_style="B", font_size_pt=t, color="#1F3864",
                                  t_margin=6 if n < 3 else 4, b_margin=2)
               for n, t in tamanhos.items()}
    estilos["li"] = TextStyle(t_margin=2.5, l_margin=5, b_margin=0)
    estilos["p"] = TextStyle(t_margin=0, b_margin=2.5)
    estilos["pre"] = TextStyle(font_family="Courier", t_margin=3, b_margin=3)
    return estilos


def blocos_para_pdf(blocos: list[Bloco], dst: Path, titulo: str, options: dict) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.set_title(titulo)
    pdf.set_creator("Lotus")
    pdf.add_page()
    fonte = next((p for p in _FONT_CANDIDATES if p.is_file()), None)
    corpo = para_html(blocos, titulo).split("<body>", 1)[-1].rsplit("</body>", 1)[0]
    if fonte:
        variantes = _VARIANTES.get(fonte.name, ())
        for estilo, nome in zip(("B", "I", "BI"), variantes or ("", "", "")):
            arquivo = fonte.with_name(nome) if nome else fonte
            pdf.add_font("Texto", estilo, str(arquivo if arquivo.is_file() else fonte))
        pdf.add_font("Texto", "", str(fonte))
        familia = "Texto"
    else:
        familia = "helvetica"
        seguro = corpo.encode("latin-1", errors="replace").decode("latin-1")
        if seguro != corpo:
            _avisar(options, 'Nenhuma fonte Unicode encontrada; alguns caracteres viraram "?".')
        corpo = seguro
    pdf.set_font(familia, size=11)
    try:
        pdf.write_html(corpo, font_family=familia, warn_on_tags_not_matching=False,
                       li_prefix_color=(60, 60, 60), tag_styles=_estilos_pdf())
    except Exception as exc:  # noqa: BLE001 - layout que o fpdf2 não desenha: cai para texto puro
        from conversor.logs import get_logger

        get_logger().exception("write_html")
        pdf = FPDF(format="A4")
        pdf.add_page()
        if fonte:
            pdf.add_font("Texto", "", str(fonte))
        pdf.set_font(familia, size=11)
        texto = para_txt(blocos)
        if not fonte:
            texto = texto.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 6, texto.replace("\t", "    "), wrapmode="CHAR")
        _avisar(options, f"A formatação não coube no PDF ({exc.__class__.__name__}); saiu como texto simples.")
    pdf.output(str(dst))


def docx_para_pdf_simples(src: Path, dst: Path, options: dict) -> None:
    """DOCX → PDF sem o Word (usado quando o Word não está instalado)."""
    blocos, avisos = ler_docx(src)
    for aviso in avisos:
        _avisar(options, aviso)
    _avisar(options, "PDF feito sem o Word: texto, títulos, listas e tabelas; o layout do Word "
                     "não. Para PDF idêntico ao Word, converta num computador com o Word.")
    blocos_para_pdf(blocos, dst, src.stem, options)


# ---------- registros ----------

NOTA_DOCX = "Sem Word: títulos, listas, tabelas, links e negrito/itálico viram estilos do Word."
NOTA_PDF = "Sem Word: títulos, listas, tabelas e links; layout simples em A4."


@register(["txt", "md", "html"], ["docx"], category="Documento", notes=NOTA_DOCX)
def texto_para_docx(src: Path, dst: Path, options: dict) -> None:
    blocos = _blocos_da_origem(src, options)
    if not blocos:
        raise ConversionError(f"{src.name} não tem texto para converter.")
    removidos = escrever_docx(blocos, dst, src.stem)
    if removidos:
        _avisar(options, f"{removidos} caractere(s) de controle invisíveis foram removidos "
                         "(o Word não os aceita).")


@register(["md", "html"], ["pdf"], category="Documento", notes=NOTA_PDF)
def texto_para_pdf(src: Path, dst: Path, options: dict) -> None:
    blocos = _blocos_da_origem(src, options)
    if not blocos:
        raise ConversionError(f"{src.name} não tem texto para converter.")
    blocos_para_pdf(blocos, dst, src.stem, options)


@register(["html"], ["txt", "md"], category="Documento", notes="Só o texto e a estrutura da página.")
@register(["md"], ["txt"], category="Documento", notes="Tira a marcação; mantém listas e tabelas.")
def texto_para_texto(src: Path, dst: Path, options: dict) -> None:
    blocos = _blocos_da_origem(src, options)
    saida = para_txt(blocos) if dst.suffix == ".txt" else para_md(blocos)
    dst.write_text(saida, encoding="utf-8")
