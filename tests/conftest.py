"""Gera arquivos de exemplo reais para cada formato de origem.

Nada de arquivos "falsos": cada amostra é produzida pela própria biblioteca
ou pelo ffmpeg, para que o teste exercite o caminho real de conversão.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

# O log de erros dos testes vai para uma pasta temporária, não para a do usuário.
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="lotus-test-log-")
# Idem para a configuração do atalho (%APPDATA%\Lotus\config.json).
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="lotus-test-config-")

HAS_FFMPEG = shutil.which("ffmpeg") is not None

CSV_TEXT = 'nome;cep;preço\nJoão;01234-000;10,50\nAna;"=SOMA(1;2)";7\n'
JSON_DATA = [
    {"nome": "João", "cep": "01234-000", "itens": [1, 2]},
    {"nome": "Ana", "idade": 30},
]


def make_sample(fmt: str, folder: Path) -> Path:
    path = folder / f"amostra.{fmt}"
    if fmt in {"png", "webp", "gif", "tiff", "ico", "avif"}:
        im = Image.new("RGBA", (64, 48), (255, 0, 0, 128))
        im.save(path)
    elif fmt == "heic":
        make_heic(path, [Image.new("RGB", (64, 48), (0, 128, 255))])
    elif fmt in {"jpg", "bmp"}:
        Image.new("RGB", (64, 48), (0, 128, 255)).save(path)
    elif fmt == "csv":
        path.write_text(CSV_TEXT, encoding="utf-8")
    elif fmt == "json":
        path.write_text(json.dumps(JSON_DATA, ensure_ascii=False), encoding="utf-8")
    elif fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["nome", "valor"])
        ws.append(["Café", 3.5])
        wb.save(path)
    elif fmt == "txt":
        path.write_text("Olá, ação e coração.\n\tLinha com tab.\n" + "x" * 300, encoding="utf-8")
    elif fmt == "md":
        path.write_text("# Título\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    elif fmt == "pdf":
        make_pdf(path, ["Página 1: ação e coração", "Página 2: São Paulo"])
    elif fmt == "docx":
        make_docx(path, "Petição: ação de cobrança")
    elif fmt == "pptx":
        make_pptx(path)
    elif fmt == "odt":
        make_opendocument(path, "application/vnd.oasis.opendocument.text")
    elif fmt == "odp":
        make_opendocument(path, "application/vnd.oasis.opendocument.presentation")
    elif fmt == "rtf":
        path.write_bytes(b"{\\rtf1\\ansi Peti\\'e7\\'e3o: a\\'e7\\'e3o de cobran\\'e7a\\par}")
    elif fmt in {"doc", "ppt"}:
        # Office 97–2003 só se cria com o próprio Word/PowerPoint.
        pytest.skip(f"amostra .{fmt} exige o Office para ser criada")
    elif fmt in {"mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "aiff"}:
        _ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1"], path)
    elif fmt in {"mp4", "mkv", "webm", "avi", "mov", "wmv", "mpeg", "m4v"}:
        # MPEG-2 só aceita taxas padrão (25 aqui); os outros usam 10 quadros/s.
        taxa = 25 if fmt == "mpeg" else 10
        _ffmpeg(
            [
                "-f", "lavfi", "-i", f"testsrc=size=64x48:rate={taxa}:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-pix_fmt", "yuv420p", "-shortest",
            ],
            path,
        )
    else:
        raise ValueError(f"sem gerador de amostra para {fmt}: adicione em conftest.py")
    return path


def make_heic(path: Path, imagens: list) -> Path:
    """HEIC real. O pillow-heif (só nos testes) tem o codificador HEVC; o app
    usa o pi-heif, que só lê. O leitor do pillow-heif NÃO é registrado aqui,
    para que a conversão use o mesmo leitor do app."""
    pillow_heif = pytest.importorskip("pillow_heif", reason="pillow-heif cria as amostras HEIC")
    heif = pillow_heif.from_pillow(imagens[0])
    for extra in imagens[1:]:
        heif.add_from_pillow(extra)
    heif.save(path, quality=95)
    return path


def make_pdf(path: Path, paginas: list[str]) -> Path:
    """PDF real com texto (fonte Unicode quando houver, para os acentos)."""
    from fpdf import FPDF

    from conversor.converters.documents import _FONT_CANDIDATES

    pdf = FPDF(format="A4")
    fonte = next((f for f in _FONT_CANDIDATES if f.is_file()), None)
    if fonte:
        pdf.add_font("T", fname=str(fonte))
    for texto in paginas:
        pdf.add_page()
        pdf.set_font("T" if fonte else "Helvetica", size=14)
        pdf.cell(0, 10, texto)
    pdf.output(str(path))
    return path


def make_docx(path: Path, texto: str) -> Path:
    """DOCX mínimo válido (3 partes obrigatórias do formato), sem depender do Word."""
    import zipfile
    from xml.sax.saxutils import escape

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'))
        z.writestr("word/document.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{escape(texto)}</w:t></w:r></w:p></w:body></w:document>'))
    return path


_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_PR = "http://schemas.openxmlformats.org/package/2006/relationships"
_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WN = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx_rico(path: Path) -> Path:
    """DOCX como o Word em português grava: estilo de título com ID localizado
    ("Ttulo1" → nome "heading 1"), negrito/itálico, link, listas, tabela,
    imagem e rodapé."""
    import zipfile

    w = f'xmlns:w="{_WN}" xmlns:r="{_RT}"'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?><w:document {w}><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:r><w:t>Petição inicial</w:t></w:r></w:p>'
           '<w:p><w:r><w:t xml:space="preserve">Texto com </w:t></w:r>'
           '<w:r><w:rPr><w:b/></w:rPr><w:t>negrito</w:t></w:r><w:r><w:t xml:space="preserve"> e </w:t></w:r>'
           '<w:r><w:rPr><w:i/></w:rPr><w:t>itálico</w:t></w:r><w:r><w:t xml:space="preserve">, veja </w:t></w:r>'
           '<w:hyperlink r:id="rIdLink"><w:r><w:t>o site</w:t></w:r></w:hyperlink><w:r><w:t>.</w:t></w:r></w:p>'
           '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
           '<w:r><w:t>Primeiro pedido</w:t></w:r></w:p>'
           '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
           '<w:r><w:t>Segundo pedido</w:t></w:r></w:p>'
           '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>'
           '<w:r><w:t>Tópico solto</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Nome</w:t></w:r></w:p></w:tc>'
           '<w:tc><w:p><w:r><w:t>Valor</w:t></w:r></w:p></w:tc></w:tr>'
           '<w:tr><w:tc><w:p><w:r><w:t>Custas</w:t></w:r></w:p></w:tc>'
           '<w:tc><w:p><w:r><w:t>R$ 10,50</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
           '<w:p><w:r><w:drawing/></w:r></w:p>'
           '<w:p><w:del><w:r><w:delText>apagado</w:delText></w:r></w:del><w:r><w:t>Fim</w:t></w:r></w:p>'
           '</w:body></w:document>')
    estilos = (f'<?xml version="1.0" encoding="UTF-8"?><w:styles {w}>'
               '<w:style w:type="paragraph" w:styleId="Ttulo1"><w:name w:val="heading 1"/></w:style>'
               '</w:styles>')
    numeracao = (f'<?xml version="1.0" encoding="UTF-8"?><w:numbering {w}>'
                 '<w:abstractNum w:abstractNumId="10"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>'
                 '</w:abstractNum><w:abstractNum w:abstractNumId="20"><w:lvl w:ilvl="0">'
                 '<w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>'
                 '<w:num w:numId="2"><w:abstractNumId w:val="20"/></w:num></w:numbering>')
    rels = (f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{_PR}">'
            f'<Relationship Id="rIdLink" Type="{_RT}/hyperlink" Target="https://exemplo.com.br/a b" '
            'TargetMode="External"/></Relationships>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", f'<?xml version="1.0"?><Types xmlns="{_CT}"/>')
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", estilos)
        z.writestr("word/numbering.xml", numeracao)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/footer1.xml", f'<w:ftr {w}><w:p><w:r><w:t>Página 1</w:t></w:r></w:p></w:ftr>')
    return path


def make_pptx(path: Path) -> Path:
    """PPTX com 2 slides: título + tópicos (com recuo) + notas; tabela + imagem."""
    import zipfile

    ns = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
          f'xmlns:r="{_RT}"')

    def sp(tipo, paras):
        ph = f'<p:ph type="{tipo}"/>' if tipo else ""
        corpo = "".join(f'<a:p><a:pPr lvl="{nv}"/><a:r><a:t>{t}</a:t></a:r></a:p>' for t, nv in paras)
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="x"/><p:cNvSpPr/><p:nvPr>{ph}</p:nvPr></p:nvSpPr>'
                f'<p:txBody>{corpo}</p:txBody></p:sp>')

    s1 = (f'<p:sld {ns}><p:cSld><p:spTree>' + sp("title", [("Audiência de conciliação", 0)])
          + sp("body", [("Pauta do dia", 0), ("Proposta de acordo", 1)]) + '</p:spTree></p:cSld></p:sld>')
    s2 = (f'<p:sld {ns} show="0"><p:cSld><p:spTree>' + sp("title", [("Valores", 0)])
          + '<p:graphicFrame><a:graphic><a:graphicData><a:tbl>'
          '<a:tr><a:tc><a:txBody><a:p><a:r><a:t>Item</a:t></a:r></a:p></a:txBody></a:tc>'
          '<a:tc><a:txBody><a:p><a:r><a:t>R$</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
          '</a:tbl></a:graphicData></a:graphic></p:graphicFrame><p:pic/></p:spTree></p:cSld></p:sld>')
    notas = (f'<p:notes {ns}><p:cSld><p:spTree>' + sp("sldImg", [])
             + sp("body", [("Lembrar do prazo", 0)]) + '</p:spTree></p:cSld></p:notes>')
    pres = (f'<p:presentation {ns}><p:sldIdLst><p:sldId id="256" r:id="rId2"/>'
            '<p:sldId id="257" r:id="rId3"/></p:sldIdLst></p:presentation>')
    rels_pres = (f'<Relationships xmlns="{_PR}">'
                 f'<Relationship Id="rId2" Type="{_RT}/slide" Target="slides/slide1.xml"/>'
                 f'<Relationship Id="rId3" Type="{_RT}/slide" Target="slides/slide2.xml"/></Relationships>')
    rels_s1 = (f'<Relationships xmlns="{_PR}"><Relationship Id="rId9" Type="{_RT}/notesSlide" '
               'Target="../notesSlides/notesSlide1.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", f'<?xml version="1.0"?><Types xmlns="{_CT}"/>')
        z.writestr("ppt/presentation.xml", pres)
        z.writestr("ppt/_rels/presentation.xml.rels", rels_pres)
        z.writestr("ppt/slides/slide1.xml", s1)
        z.writestr("ppt/slides/slide2.xml", s2)
        z.writestr("ppt/slides/_rels/slide1.xml.rels", rels_s1)
        z.writestr("ppt/notesSlides/notesSlide1.xml", notas)
    return path


def make_opendocument(path: Path, mime: str) -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", mime)  # 1º arquivo, como manda o formato
        z.writestr("content.xml", "<office:document-content/>")
    return path


def _ffmpeg(args: list[str], out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *args, str(out)],
        check=True,
    )


@pytest.fixture
def sample(tmp_path):
    def _make(fmt: str) -> Path:
        d = tmp_path / f"src_{fmt}"
        d.mkdir(exist_ok=True)
        return make_sample(fmt, d)

    return _make


_DIALOGOS = {
    "messagebox": [("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"),
                   ("askyesno", False), ("askokcancel", False), ("askyesnocancel", None),
                   ("askquestion", "no"), ("askretrycancel", False)],
    "colorchooser": [("askcolor", (None, None))],
    "filedialog": [("askopenfilenames", ""), ("askopenfilename", ""), ("askdirectory", ""),
                   ("asksaveasfilename", "")],
}


@pytest.fixture(autouse=True)
def _sem_dialogos_reais(monkeypatch):
    """Uma caixa de diálogo real trava o teste até alguém clicar (no Mac é um
    alerta nativo modal: o CI ficou parado 14 min). Aqui o diálogo só é
    registrado no stderr do teste. Testes que conferem um diálogo fazem o
    próprio monkeypatch por cima deste."""
    try:
        import importlib

        modulos = {n: importlib.import_module(f"tkinter.{n}") for n in _DIALOGOS}
    except ImportError:
        return

    def falso(nome, resposta):
        def f(*args, **kwargs):
            print(f"[diálogo {nome}] {args} {kwargs.get('message', '')}", file=sys.stderr)
            return resposta
        return f

    for mod, funcs in _DIALOGOS.items():
        for nome, resposta in funcs:
            monkeypatch.setattr(modulos[mod], nome, falso(nome, resposta))


# ---------- erros do Tcl em segundo plano ----------
# Erro num script Tcl de evento (after, binding) chama o comando `bgerror`;
# o padrão do Tk (bgerror.tcl, carregado sob demanda) abre um diálogo com
# grab + vwait que trava o teste dentro do update() — no Mac isso apareceu
# como travamento sem nenhuma linha Python na pilha. Aqui o `bgerror` é
# nosso: registra a mensagem e a pilha Tcl, e o teste falha mostrando-as.
ERROS_TCL: list[str] = []

try:
    import tkinter as _tk
except ImportError:  # pragma: no cover
    _tk = None

if _tk is not None:
    _tk_init_original = _tk.Tk.__init__

    def _tk_init_com_bgerror(self, *args, **kwargs):
        _tk_init_original(self, *args, **kwargs)

        def bgerror(msg):
            try:
                pilha = self.tk.globalgetvar("errorInfo")
            except _tk.TclError:
                pilha = ""
            ERROS_TCL.append(f"{msg}\n{pilha}")
            print(f"[bgerror do Tk] {msg}\n{pilha}", file=sys.stderr)

        self.tk.createcommand("bgerror", bgerror)

    _tk.Tk.__init__ = _tk_init_com_bgerror


@pytest.fixture(autouse=True)
def _sem_erros_tcl():
    ERROS_TCL.clear()
    yield
    erros, ERROS_TCL[:] = list(ERROS_TCL), []
    assert not erros, "erro do Tcl em segundo plano:\n" + "\n---\n".join(erros)


# ---------- vigia de travamento (só no Mac) ----------
# No CI do Mac, update() do Tk às vezes fica preso em código nativo (a pilha
# do Python não mostra o motivo). Se um teste passar do limite, gravamos a
# pilha NATIVA de todas as threads com o `sample` do macOS e encerramos o
# processo, em vez de esperar o limite do CI.
_LIMITE_TESTE_S = 90


@pytest.fixture(autouse=True)
def _vigia_travamento_mac(request):
    if sys.platform != "darwin":
        yield
        return
    import faulthandler
    import threading

    feito = threading.Event()
    destino = Path(os.environ.get("LOTUS_TRAVAMENTO", "travamento-mac.txt")).resolve()

    def vigiar():
        if feito.wait(_LIMITE_TESTE_S):
            return
        with open(destino, "w", encoding="utf-8") as f:
            f.write(f"Teste travado há {_LIMITE_TESTE_S} s: {request.node.nodeid}\n\n== Python ==\n")
            f.flush()
            faulthandler.dump_traceback(file=f, all_threads=True)
            for cmd in (["/usr/bin/sample", str(os.getpid()), "3"],
                        ["sudo", "-n", "/usr/bin/sample", str(os.getpid()), "3"]):
                f.write(f"\n== {' '.join(cmd)} ==\n")
                f.flush()
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                    f.write(r.stdout + r.stderr)
                    if r.returncode == 0:
                        break
                except Exception as e:  # noqa: BLE001 - diagnóstico, nunca derrubar aqui
                    f.write(f"falhou: {e!r}\n")
        os._exit(3)

    threading.Thread(target=vigiar, name="vigia-travamento", daemon=True).start()
    yield
    feito.set()


# ---------- update() limitado nos testes do Mac ----------
# A pilha nativa (sample) do CI do Mac mostrou o comando `update` do Tk
# chamando Tcl_DoOneEvent sem fim: o notificador Cocoa do Tcl sempre tem
# mais um evento pronto, então "processar até a fila esvaziar" nunca acaba.
# O app não usa update() (só mainloop, que não precisa da fila vazia);
# nos testes, update() vira: tarefas ociosas + até 2000 eventos prontos.
if _tk is not None and sys.platform == "darwin":
    import _tkinter

    def _update_limitado(self):
        self.update_idletasks()
        for _ in range(2000):
            if not self.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
                break
        self.update_idletasks()

    _tk.Misc.update = _update_limitado
