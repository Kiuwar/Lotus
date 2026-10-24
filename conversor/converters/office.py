"""Conversões feitas pelo Microsoft Word e pelo PowerPoint instalados (só Windows).

Word: DOCX, DOC, RTF e ODT entre si e para PDF/XPS (igual a "Salvar como");
PDF → DOCX pelo "PDF Reflow" do Word (layout aproximado, com aviso).
PowerPoint: PPTX, PPT e ODP entre si e para PDF; uma imagem PNG/JPG por slide.

Sem o programa, as conversões aparecem como indisponíveis (padrão do ffmpeg).
Constantes conferidas em learn.microsoft.com (VBA):
  WdSaveFormat: wdFormatDocument97 = 0, wdFormatRTF = 6, wdFormatDocumentDefault = 16,
    wdFormatPDF = 17, wdFormatXPS = 18, wdFormatOpenDocumentText = 23
  WdAlertLevel: wdAlertsNone = 0;  WdSaveOptions: wdDoNotSaveChanges = 0
  PpSaveAsFileType: ppSaveAsPresentation = 1, ppSaveAsOpenXMLPresentation = 24,
    ppSaveAsPDF = 32, ppSaveAsOpenDocumentPresentation = 35
  MsoTriState: msoTrue = -1, msoFalse = 0
  Presentation.SaveAs(FileName, FileFormat); Presentations.Open(FileName, ReadOnly,
    Untitled, WithWindow); Slide.Export(FileName, FilterName, ScaleWidth, ScaleHeight)
"""

from __future__ import annotations

import csv
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

from conversor.core.engine import ConversionError
from conversor.core.registry import register
from conversor.logs import get_logger

WD_FORMAT_DOC = 0
WD_FORMAT_RTF = 6
WD_FORMAT_DOCX = 16
WD_FORMAT_PDF = 17
WD_FORMAT_XPS = 18
WD_FORMAT_ODT = 23
WD_FORMATOS = {"doc": WD_FORMAT_DOC, "rtf": WD_FORMAT_RTF, "docx": WD_FORMAT_DOCX,
               "pdf": WD_FORMAT_PDF, "xps": WD_FORMAT_XPS, "odt": WD_FORMAT_ODT}
WD_ALERTS_NONE = 0
WD_DO_NOT_SAVE = 0

PP_FORMATOS = {"ppt": 1, "pptx": 24, "pdf": 32, "odp": 35}
MSO_TRUE, MSO_FALSE = -1, 0
LARGURA_SLIDE_PX = 1920  # imagem de cada slide (altura pela proporção do slide)

LIMITE_SEGUNDOS = 180

NOTES = "Requer o Microsoft Word instalado neste computador."
NOTES_PPT = "Requer o Microsoft PowerPoint instalado neste computador."


def _registrado(prog_id: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\CLSID"):
            return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def word_disponivel() -> bool:
    return _registrado("Word.Application")


@lru_cache(maxsize=1)
def powerpoint_disponivel() -> bool:
    return _registrado("PowerPoint.Application")


# ---------- pontos substituíveis nos testes ----------

def _criar_word():
    import win32com.client

    # DispatchEx: abre uma instância NOVA, sem mexer no Word que o usuário tem aberto.
    return win32com.client.DispatchEx("Word.Application")


def _com_iniciar() -> None:
    import pythoncom

    pythoncom.CoInitialize()


def _com_encerrar() -> None:
    import pythoncom

    pythoncom.CoUninitialize()


def _criar_powerpoint():
    import win32com.client

    return win32com.client.DispatchEx("PowerPoint.Application")


def _pids_word() -> set[int]:
    return _pids("WINWORD.EXE")


def _pids_powerpoint() -> set[int]:
    return _pids("POWERPNT.EXE")


def _pids(imagem: str) -> set[int]:
    """PIDs do programa em execução (para saber qual instância é a nossa)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {imagem}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except OSError:
        return set()
    # Formato: "WINWORD.EXE","1234","Console","1","123.456 K"
    return {int(c[1]) for c in csv.reader(out.splitlines()) if len(c) > 1 and c[1].isdigit()}


def _encerrar_pids(pids: set[int]) -> None:
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------- conversão ----------

def _com_limite(nome: str, criar, listar_pids, src: Path, limite: float, trabalho, fechar) -> None:
    """Abre uma instância NOVA do programa (COM), executa `trabalho(app)` e fecha.
    Travou além do limite? Encerra só a instância aberta pelo Lotus."""
    log = get_logger()
    antes = listar_pids()
    _com_iniciar()
    app = None
    estourou = threading.Event()
    nossos: set[int] = set()

    def vigia() -> None:
        estourou.set()
        log.error("%s não respondeu em %ss; encerrando a instância aberta pelo Lotus %s", nome, limite, nossos)
        _encerrar_pids(nossos)

    timer = threading.Timer(limite, vigia)
    try:
        app = criar()
        nossos.update(listar_pids() - antes)  # nunca inclui um programa que já estava aberto
        timer.start()
        trabalho(app)
    except Exception as e:
        if estourou.is_set():
            raise ConversionError(
                f"O {nome} não terminou de converter {src.name} em {limite // 60} minutos e foi "
                f"encerrado. Como resolver: abra o arquivo no {nome} e use Salvar como."
            ) from e
        if isinstance(e, ConversionError):
            raise
        raise ConversionError(f"O {nome} não conseguiu converter {src.name}: {e}") from e
    finally:
        timer.cancel()
        if app is not None and not estourou.is_set():
            try:
                fechar(app)
            except Exception:
                log.exception("falha ao fechar o %s", nome)
        _com_encerrar()


def _converter_com_word(src: Path, dst: Path, formato: int, limite: float = LIMITE_SEGUNDOS) -> None:
    def trabalho(word):
        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        doc = word.Documents.Open(
            FileName=str(src), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False
        )
        try:
            doc.SaveAs2(FileName=str(dst), FileFormat=formato, AddToRecentFiles=False)
        finally:
            doc.Close(SaveChanges=WD_DO_NOT_SAVE)

    _com_limite("Word", _criar_word, _pids_word, src, limite, trabalho,
                lambda w: w.Quit(SaveChanges=WD_DO_NOT_SAVE))


def _converter_com_powerpoint(src: Path, dst: Path, alvo: str, limite: float = LIMITE_SEGUNDOS) -> None:
    """alvo em PP_FORMATOS (Salvar como) ou "png"/"jpg" (dst é a pasta das imagens)."""
    def trabalho(pp):
        # Sem janela: WithWindow=msoFalse (esconder o aplicativo inteiro não é permitido).
        pres = pp.Presentations.Open(FileName=str(src), ReadOnly=MSO_TRUE, Untitled=MSO_FALSE,
                                     WithWindow=MSO_FALSE)
        try:
            if alvo in PP_FORMATOS:
                pres.SaveAs(FileName=str(dst), FileFormat=PP_FORMATOS[alvo])
                return
            total = pres.Slides.Count
            if total == 0:
                raise ConversionError(f"{src.name} não tem slides.")
            largura = LARGURA_SLIDE_PX
            altura = round(largura * pres.PageSetup.SlideHeight / pres.PageSetup.SlideWidth)
            digitos = max(3, len(str(total)))
            for i in range(1, total + 1):
                destino = dst / f"slide_{i:0{digitos}d}.{alvo}"
                pres.Slides.Item(i).Export(str(destino), alvo.upper(), largura, altura)
        finally:
            pres.Close()

    _com_limite("PowerPoint", _criar_powerpoint, _pids_powerpoint, src, limite, trabalho,
                lambda p: p.Quit())


@register(["docx", "doc", "rtf", "odt"], ["pdf", "docx", "doc", "rtf", "odt", "xps"],
          category="Word", notes=NOTES, available=word_disponivel)
def word_salvar_como(src: Path, dst: Path, options: dict) -> None:
    _converter_com_word(src.resolve(), dst.resolve(), WD_FORMATOS[dst.suffix.lstrip(".")])


@register(["pdf"], ["docx"], category="Word", notes=NOTES, available=word_disponivel)
def pdf_para_docx(src: Path, dst: Path, options: dict) -> None:
    _converter_com_word(src.resolve(), dst.resolve(), WD_FORMAT_DOCX)
    options.setdefault("_warnings", []).append(
        f"{src.name}: o Word reconstrói o PDF como texto editável; o layout pode mudar. Confira o documento."
    )


@register(["pptx", "ppt", "odp"], ["pdf", "pptx", "ppt", "odp"],
          category="PowerPoint", notes=NOTES_PPT, available=powerpoint_disponivel)
def powerpoint_salvar_como(src: Path, dst: Path, options: dict) -> None:
    _converter_com_powerpoint(src.resolve(), dst.resolve(), dst.suffix.lstrip("."))


@register(["pptx", "ppt", "odp"], ["png", "jpg"], category="PowerPoint", multi=True,
          notes="Uma imagem por slide (1920 px de largura). " + NOTES_PPT, available=powerpoint_disponivel)
def powerpoint_para_imagens(src: Path, pasta: Path, options: dict) -> None:
    alvo = "png" if (options.get("_target") or "png") == "png" else "jpg"
    _converter_com_powerpoint(src.resolve(), pasta.resolve(), alvo)
