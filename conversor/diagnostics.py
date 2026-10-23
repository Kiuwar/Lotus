"""Diagnóstico e reparo da instalação.

Verifica o que costuma quebrar depois de instalado:
- menu do botão direito apontando para um .exe que foi movido/atualizado;
- ffmpeg ausente (áudio/vídeo indisponíveis);
- pasta de log sem permissão de escrita.
Só repara o que foi instalado antes: não instala o menu sem o usuário pedir.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from conversor import shell
from conversor.converters import media
from conversor.logs import log_dir


def menu_state(winreg_module=None, root_prefix: str = "") -> tuple[bool, list[str]]:
    """(menu instalado?, problemas encontrados)."""
    entries = shell.build_entries()
    problems = shell.inspect(entries, winreg_module, root_prefix)
    roots = set(shell.menu_roots(entries))
    missing_roots = {p.removeprefix("chave ausente: ") for p in problems} & roots
    installed = len(missing_roots) < len(roots)
    return installed, problems


def repair_menu(winreg_module=None, root_prefix: str = "") -> str:
    installed, problems = menu_state(winreg_module, root_prefix)
    if not installed:
        return "Menu do botão direito: não instalado (nada a reparar)."
    if not problems:
        return "Menu do botão direito: ok."
    shell.install(winreg_module=winreg_module, root_prefix=root_prefix)
    _, after = menu_state(winreg_module, root_prefix)
    if after:
        return f"Menu do botão direito: reparo FALHOU ({len(after)} problemas restantes)."
    return f"Menu do botão direito: reparado ({len(problems)} problemas corrigidos)."


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder):
            pass
        return True
    except OSError:
        return False


def run(winreg_module=None, root_prefix: str = "") -> list[str]:
    report = []
    if sys.platform == "win32" or winreg_module is not None:
        try:
            report.append(repair_menu(winreg_module, root_prefix))
        except OSError as e:
            report.append(f"Menu do botão direito: erro ao acessar o registro ({e}).")
    media.ffmpeg_path.cache_clear()
    ff = media.ffmpeg_path()
    report.append(
        f"ffmpeg: encontrado em {ff}." if ff
        else "ffmpeg: não encontrado — áudio e vídeo indisponíveis (veja o README, seção ffmpeg)."
    )
    report.append(
        f"Pasta de log: ok ({log_dir()})." if _writable(log_dir())
        else f"Pasta de log: sem permissão de escrita ({log_dir()})."
    )
    report.append(
        "Pasta temporária: ok." if _writable(Path(tempfile.gettempdir()))
        else "Pasta temporária: sem permissão de escrita."
    )
    return report
