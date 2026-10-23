"""Conversões feitas pelo Microsoft Word instalado no computador (só Windows).

- DOCX → PDF: igual a "Salvar como PDF" do Word.
- PDF → DOCX: o Word reconstrói o documento a partir do PDF ("PDF Reflow").
  O layout fica aproximado; o usuário é avisado.

Sem Word, essas conversões aparecem como indisponíveis (mesmo padrão do ffmpeg).
Constantes conferidas em learn.microsoft.com (Word VBA):
  WdSaveFormat: wdFormatDocumentDefault = 16 (DOCX), wdFormatPDF = 17
  WdAlertLevel: wdAlertsNone = 0;  WdSaveOptions: wdDoNotSaveChanges = 0
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

WD_FORMAT_DOCX = 16
WD_FORMAT_PDF = 17
WD_ALERTS_NONE = 0
WD_DO_NOT_SAVE = 0
LIMITE_SEGUNDOS = 180

NOTES = "Requer o Microsoft Word instalado neste computador."


@lru_cache(maxsize=1)
def word_disponivel() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"):
            return True
    except OSError:
        return False


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


def _pids_word() -> set[int]:
    """PIDs de WINWORD.EXE em execução (para saber qual instância é a nossa)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
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

def _converter_com_word(src: Path, dst: Path, formato: int, limite: float = LIMITE_SEGUNDOS) -> None:
    log = get_logger()
    antes = _pids_word()
    _com_iniciar()
    word = None
    estourou = threading.Event()
    nossos: set[int] = set()

    def vigia() -> None:
        estourou.set()
        log.error("Word não respondeu em %ss; encerrando a instância aberta pelo Lotus %s", limite, nossos)
        _encerrar_pids(nossos)

    timer = threading.Timer(limite, vigia)
    try:
        word = _criar_word()
        nossos.update(_pids_word() - antes)  # nunca inclui um Word que já estava aberto
        timer.start()
        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        doc = word.Documents.Open(
            FileName=str(src), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False
        )
        try:
            doc.SaveAs2(FileName=str(dst), FileFormat=formato, AddToRecentFiles=False)
        finally:
            doc.Close(SaveChanges=WD_DO_NOT_SAVE)
    except Exception as e:
        if estourou.is_set():
            raise ConversionError(
                f"O Word não terminou de converter {src.name} em {limite // 60} minutos e foi "
                "encerrado. Como resolver: abra o arquivo no Word e use Salvar como."
            ) from e
        raise ConversionError(f"O Word não conseguiu converter {src.name}: {e}") from e
    finally:
        timer.cancel()
        if word is not None and not estourou.is_set():
            try:
                word.Quit(SaveChanges=WD_DO_NOT_SAVE)
            except Exception:
                log.exception("falha ao fechar o Word")
        _com_encerrar()


@register(["docx"], ["pdf"], category="Word", notes=NOTES, available=word_disponivel)
def docx_para_pdf(src: Path, dst: Path, options: dict) -> None:
    _converter_com_word(src.resolve(), dst.resolve(), WD_FORMAT_PDF)


@register(["pdf"], ["docx"], category="Word", notes=NOTES, available=word_disponivel)
def pdf_para_docx(src: Path, dst: Path, options: dict) -> None:
    _converter_com_word(src.resolve(), dst.resolve(), WD_FORMAT_DOCX)
    options.setdefault("_warnings", []).append(
        f"{src.name}: o Word reconstrói o PDF como texto editável; o layout pode mudar. Confira o documento."
    )
