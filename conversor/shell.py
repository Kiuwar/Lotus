"""Menu de contexto do Windows Explorer (botão direito do mouse).

Registra, por usuário (HKEY_CURRENT_USER, sem precisar de administrador),
um submenu "Converter para" em cada tipo de arquivo suportado:

    HKCU\\Software\\Classes\\SystemFileAssociations\\.png\\shell\\Lotus.Converter
        MUIVerb     = "Converter para"
        SubCommands = ""            (vazio = os itens vêm da subchave "shell")
        shell\\10_jpg     MUIVerb = "JPG"   command = "Lotus.exe" --menu-converter jpg "%1"
        shell\\99_escolher MUIVerb = "Escolher formato…"   command = ... --menu-escolher "%1"

No Windows 11 o item aparece em "Mostrar mais opções" (menu clássico); o menu
novo do Windows 11 só aceita extensões com identidade de pacote (MSIX).

A montagem das chaves (`build_entries`) é pura e testável em qualquer sistema.
Só `install`/`uninstall`/`inspect` tocam o registro, via o módulo `winreg`,
que pode ser substituído nos testes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from conversor.core import registry
from conversor.core.detect import ALIASES

VERB = "Lotus.Converter"
CLASSES_ROOT = r"Software\Classes"
MENU_LABEL = "Converter para"
CHOOSER_LABEL = "Escolher formato…"


@dataclass
class Entry:
    key: str  # caminho relativo à raiz (ex.: Software\Classes)
    values: dict[str, str] = field(default_factory=dict)  # "" = valor padrão


def launcher_command() -> list[str]:
    """Programa que o Explorer deve chamar (sem argumentos)."""
    if getattr(sys, "frozen", False):  # executável do PyInstaller
        # Mesmo se chamado pelo conversor-cli.exe, o menu deve abrir o Lotus.exe
        # (com janela), que fica na mesma pasta.
        gui = Path(sys.executable).with_name("Lotus.exe")
        return [str(gui if gui.is_file() else sys.executable)]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")  # evita abrir janela de console
    script = Path(__file__).resolve().parent.parent / "packaging" / "app_gui.py"
    return [str(pythonw if pythonw.is_file() else exe), str(script)]


def _quote(parts: list[str]) -> str:
    return " ".join(f'"{p}"' for p in parts)


def source_extensions() -> dict[str, str]:
    """extensão no Windows -> formato canônico (inclui apelidos como .jpeg)."""
    canon = sorted({c.source for c in registry.all_converters()})
    exts = {f: f for f in canon}
    for alias, real in ALIASES.items():
        if real in exts:
            exts[alias] = real
    return dict(sorted(exts.items()))


def build_entries(launcher: list[str] | None = None) -> list[Entry]:
    launcher = launcher or launcher_command()
    base_cmd = _quote(launcher)
    icon = f"{launcher[0]},0"
    entries: list[Entry] = []
    for ext, fmt in source_extensions().items():
        targets = registry.targets_for(fmt, only_available=False)
        if not targets:
            continue
        root = rf"{CLASSES_ROOT}\SystemFileAssociations\.{ext}\shell\{VERB}"
        entries.append(Entry(root, {"MUIVerb": MENU_LABEL, "SubCommands": "", "Icon": icon}))
        # Prefixo numérico: o Explorer ordena os subitens pelo nome da chave.
        for i, target in enumerate(targets, start=10):
            sub = rf"{root}\shell\{i:02d}_{target}"
            entries.append(Entry(sub, {"MUIVerb": target.upper()}))
            entries.append(
                Entry(rf"{sub}\command", {"": f'{base_cmd} --menu-converter {target} "%1"'})
            )
        chooser = rf"{root}\shell\99_escolher"
        entries.append(Entry(chooser, {"MUIVerb": CHOOSER_LABEL}))
        entries.append(Entry(rf"{chooser}\command", {"": f'{base_cmd} --menu-escolher "%1"'}))
    return entries


def menu_roots(entries: list[Entry]) -> list[str]:
    return [e.key for e in entries if e.key.endswith(VERB)]


# ---------- acesso ao registro ----------

def _winreg(module=None):
    if module is not None:
        return module
    import winreg  # só existe no Windows

    return winreg


def _delete_tree(wr, hive, path: str) -> None:
    try:
        with wr.OpenKey(hive, path, 0, wr.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = wr.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(wr, hive, rf"{path}\{child}")
    except FileNotFoundError:
        return
    wr.DeleteKey(hive, path)


def _notify_explorer() -> None:
    """Avisa o Explorer que associações mudaram (SHCNE_ASSOCCHANGED)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def install(entries: list[Entry] | None = None, winreg_module=None, root_prefix: str = "") -> int:
    """Grava as chaves. Remove antes as antigas para não sobrar item órfão."""
    wr = _winreg(winreg_module)
    entries = entries if entries is not None else build_entries()
    uninstall(winreg_module=wr, root_prefix=root_prefix)
    for e in entries:
        with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, root_prefix + e.key, 0, wr.KEY_WRITE) as k:
            for name, value in e.values.items():
                wr.SetValueEx(k, name, 0, wr.REG_SZ, value)
    _notify_explorer()
    return len(menu_roots(entries))


def uninstall(winreg_module=None, root_prefix: str = "") -> int:
    """Remove o menu de todas as extensões que tenham a chave do Lotus."""
    wr = _winreg(winreg_module)
    sfa = rf"{root_prefix}{CLASSES_ROOT}\SystemFileAssociations"
    removed = 0
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, sfa) as k:
            exts = []
            i = 0
            while True:
                try:
                    exts.append(wr.EnumKey(k, i))
                except OSError:
                    break
                i += 1
    except FileNotFoundError:
        return 0
    for ext in exts:
        path = rf"{sfa}\{ext}\shell\{VERB}"
        try:
            wr.OpenKey(wr.HKEY_CURRENT_USER, path).Close()
        except FileNotFoundError:
            continue
        _delete_tree(wr, wr.HKEY_CURRENT_USER, path)
        removed += 1
    _notify_explorer()
    return removed


def inspect(entries: list[Entry] | None = None, winreg_module=None, root_prefix: str = "") -> list[str]:
    """Compara o registro com o esperado. Retorna a lista de problemas (vazia = ok)."""
    wr = _winreg(winreg_module)
    entries = entries if entries is not None else build_entries()
    problems = []
    for e in entries:
        try:
            with wr.OpenKey(wr.HKEY_CURRENT_USER, root_prefix + e.key) as k:
                for name, expected in e.values.items():
                    try:
                        value, _ = wr.QueryValueEx(k, name)
                    except FileNotFoundError:
                        problems.append(f"valor ausente: {e.key} [{name or '(padrão)'}]")
                        continue
                    if value != expected:
                        problems.append(f"valor desatualizado: {e.key} [{name or '(padrão)'}]")
        except FileNotFoundError:
            problems.append(f"chave ausente: {e.key}")
    return problems
