"""Ação Rápida do Finder "Converter com Lotus" (clique direito no Mac).

Gera um pacote .workflow em ~/Library/Services. Estrutura copiada de
workflows reais (ação "Run Shell Script" do Automator) — fontes:
- github.com/mb21/Pandoc-Mac-OS-X-Services (document.wflow com Run Shell Script);
- andrewbaker.ninja (2026-09-08): Ação Rápida do Finder com NSRequiredContext
  com.apple.finder, NSSendFileTypes e inputMethod = 1 (arquivos como argumentos).
O CI do Mac EXECUTA o workflow gerado com `automator -i` (tests/test_mac.py).
"""

from __future__ import annotations

import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

NOME = "Converter com Lotus"


def pasta_servicos() -> Path:
    return Path.home() / "Library" / "Services"


def caminho_app() -> Path | None:
    """Lotus.app quando empacotado (…/Lotus.app/Contents/MacOS/Lotus)."""
    exe = Path(sys.executable).resolve()
    for p in exe.parents:
        if p.suffix == ".app":
            return p
    return None


def comando_padrao() -> str:
    app = caminho_app()
    if app is not None:
        # `open` abre o app como app do Mac (Dock, foco) passando os arquivos.
        return f'open -n -a {shlex.quote(str(app))} --args --menu-escolher "$@"'
    script = Path(__file__).resolve().parent.parent / "packaging" / "app_gui.py"
    return f'{shlex.quote(sys.executable)} {shlex.quote(str(script))} --menu-escolher "$@"'


def _info_plist() -> bytes:
    return plistlib.dumps({
        "NSServices": [{
            "NSMenuItem": {"default": NOME},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
            "NSSendFileTypes": ["public.item"],
        }]
    })


def _document_wflow(comando: str) -> bytes:
    acao_uuid, entrada, saida = (str(uuid.uuid4()).upper() for _ in range(3))
    acao = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {"COMMAND_STRING": {}, "CheckedForUserDefaultShell": {},
                                  "inputMethod": {}, "shell": {}, "source": {}},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": comando,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,          # 1 = arquivos chegam como argumentos ("$@")
            "shell": "/bin/zsh",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": entrada,
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": saida,
        "UUID": acao_uuid,
        "UnlocalizedApplications": ["Automator"],
        "arguments": {
            "0": {"default value": 0, "name": "inputMethod", "required": "0", "type": "0", "uuid": "0"},
            "1": {"default value": "", "name": "source", "required": "0", "type": "0", "uuid": "1"},
            "2": {"default value": False, "name": "CheckedForUserDefaultShell", "required": "0",
                  "type": "0", "uuid": "2"},
            "3": {"default value": "", "name": "COMMAND_STRING", "required": "0", "type": "0", "uuid": "3"},
            "4": {"default value": "/bin/sh", "name": "shell", "required": "0", "type": "0", "uuid": "4"},
        },
        "isViewVisible": True,
    }
    return plistlib.dumps({
        "AMApplicationBuild": "523",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{"action": acao, "isViewVisible": True}],
        "connectors": {},
        "workflowMetaData": {
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": 0,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    })


def gerar(destino: Path, comando: str | None = None) -> Path:
    """Cria <destino>/Converter com Lotus.workflow e devolve o caminho."""
    wf = destino / f"{NOME}.workflow"
    if wf.exists():
        shutil.rmtree(wf)
    (wf / "Contents").mkdir(parents=True)
    (wf / "Contents" / "Info.plist").write_bytes(_info_plist())
    (wf / "Contents" / "document.wflow").write_bytes(_document_wflow(comando or comando_padrao()))
    return wf


def _atualizar_servicos() -> None:
    pbs = Path("/System/Library/CoreServices/pbs")
    if pbs.exists():
        subprocess.run([str(pbs), "-flush"], capture_output=True, timeout=20)


def instalar() -> Path:
    wf = gerar(pasta_servicos())
    _atualizar_servicos()
    return wf


def desinstalar() -> bool:
    wf = pasta_servicos() / f"{NOME}.workflow"
    if not wf.exists():
        return False
    shutil.rmtree(wf)
    _atualizar_servicos()
    return True


def instalada() -> bool:
    return (pasta_servicos() / f"{NOME}.workflow" / "Contents" / "document.wflow").is_file()
