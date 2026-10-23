"""Janelas abertas pelo menu do botão direito.

- `--menu-converter FMT arquivo`: converte direto e mostra um aviso rápido.
- `--menu-escolher arquivo`: abre uma janela com um botão por formato possível.

O Explorer abre um processo por arquivo selecionado; por isso cada janela é
pequena e independente.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from conversor.core import registry
from conversor.core.detect import DetectionError, detect
from conversor.core.engine import ConversionError, Result, convert_file
from conversor.gui import common_targets, motivo_sem_destino
from conversor.logs import log_file

TITLE = "Lotus"


@dataclass
class Outcome:
    path: Path
    result: Result | None = None
    error: str | None = None


def convert_many(paths: list[str], target: str) -> list[Outcome]:
    out = []
    for p in paths:
        try:
            out.append(Outcome(Path(p), result=convert_file(p, target)))
        except ConversionError as e:
            out.append(Outcome(Path(p), error=str(e)))
    return out


def summary(outcomes: list[Outcome]) -> tuple[bool, str]:
    """(teve erro?, texto para o usuário)."""
    lines = []
    for o in outcomes:
        if o.error:
            lines.append(f"✗ {o.error}")
        else:
            lines.append(f"✓ {o.path.name} → {o.result.output.name}")
            lines += [f"   aviso: {w}" for w in o.result.warnings]
    failed = any(o.error for o in outcomes)
    if failed:
        lines.append(f"\nDetalhes técnicos: {log_file()}")
    return failed, "\n".join(lines)


def open_folder(path: Path) -> None:
    """Abre o Explorer com o arquivo selecionado."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def open_dir(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 — abre a pasta no Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------- conversão direta (item do submenu) ----------

def toast(root: tk.Tk, text: str, ms: int = 3500) -> None:
    """Aviso discreto no canto da tela que some sozinho."""
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    frame = ttk.Frame(root, padding=12, relief="solid", borderwidth=1)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=text, justify="left", wraplength=360).pack()
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    x = root.winfo_screenwidth() - w - 24
    y = root.winfo_screenheight() - h - 72  # acima da barra de tarefas
    root.geometry(f"+{x}+{y}")
    root.bind("<Button-1>", lambda _e: root.destroy())
    root.after(ms, root.destroy)


def quick_convert(paths: list[str], target: str, root: tk.Tk | None = None) -> int:
    outcomes = convert_many(paths, target)
    failed, text = summary(outcomes)
    root = root or tk.Tk()
    if failed:
        root.withdraw()
        messagebox.showerror(TITLE, text, parent=root)
        root.destroy()
        return 1
    toast(root, f"{TITLE}: conversão concluída\n{text}")
    root.mainloop()
    return 0


# ---------- janela de escolha (item "Escolher formato…") ----------

class Chooser(ttk.Frame):
    """Um botão por formato de destino possível para os arquivos recebidos."""

    COLUMNS = 4

    def __init__(self, master: tk.Misc, paths: list[str]):
        super().__init__(master, padding=14)
        self.master = master
        # Pode estar numa janela própria (menu) ou dentro do painel flutuante.
        top = master.winfo_toplevel()
        self.paths = paths
        self.outcomes: list[Outcome] = []
        self.worker: threading.Thread | None = None
        top.title(f"{TITLE} — converter")
        top.resizable(False, False)
        self.pack(fill="both", expand=True)

        formats, problems = [], []
        for p in paths:
            try:
                formats.append(detect(Path(p)).fmt)
            except DetectionError as e:
                problems.append(str(e))
        self.targets = common_targets(formats)

        names = ", ".join(Path(p).name for p in paths[:3]) + (" …" if len(paths) > 3 else "")
        ttk.Label(self, text=f"Converter {names} para:", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=self.COLUMNS, sticky="w", pady=(0, 10)
        )

        self.buttons: dict[str, ttk.Button] = {}
        for i, t in enumerate(self.targets):
            b = ttk.Button(self, text=t.upper(), width=10, command=lambda t=t: self.start(t))
            b.grid(row=1 + i // self.COLUMNS, column=i % self.COLUMNS, padx=4, pady=4, ipady=6)
            self.buttons[t] = b
        next_row = 2 + len(self.targets) // self.COLUMNS

        if not self.targets:
            msg = "\n".join(problems) or motivo_sem_destino(formats) or ""
            ttk.Label(self, text=msg, foreground="#a00", wraplength=380).grid(
                row=next_row, column=0, columnspan=self.COLUMNS, sticky="w"
            )
        unavailable = [
            t.upper()
            for f in set(formats)
            for t in registry.targets_for(f, only_available=False)
            if t not in registry.targets_for(f)
        ]
        if unavailable:
            ttk.Label(
                self,
                text=f"Indisponíveis sem ffmpeg: {', '.join(sorted(set(unavailable)))}",
                foreground="#666",
            ).grid(row=next_row + 1, column=0, columnspan=self.COLUMNS, sticky="w", pady=(6, 0))

        self.status = ttk.Label(self, text="", wraplength=400, justify="left")
        self.status.grid(row=next_row + 2, column=0, columnspan=self.COLUMNS, sticky="w", pady=(10, 0))
        bar = ttk.Frame(self)
        bar.grid(row=next_row + 3, column=0, columnspan=self.COLUMNS, sticky="e", pady=(10, 0))
        self.open_btn = ttk.Button(bar, text="Abrir pasta", state="disabled", command=self._open)
        self.open_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="Fechar", command=top.destroy).pack(side="left")
        top.bind("<Escape>", lambda _e: top.destroy())

    def start(self, target: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        for b in self.buttons.values():
            b.configure(state="disabled")
        self.status.configure(text=f"Convertendo para {target.upper()}…", foreground="")
        # Só dados para a thread (veja o comentário equivalente em gui.App.start).
        self._results: list[Outcome] = []
        self.worker = threading.Thread(
            target=_convert_into, args=(self._results, list(self.paths), target), daemon=True
        )
        self.worker.start()
        self.after(100, self._poll)

    def _poll(self) -> None:
        if self.worker and self.worker.is_alive():
            self.after(100, self._poll)
            return
        self.outcomes = list(self._results)
        failed, text = summary(self.outcomes)
        self.status.configure(text=text, foreground="#a00" if failed else "#060")
        for b in self.buttons.values():
            b.configure(state="normal")
        if any(o.result for o in self.outcomes):
            self.open_btn.configure(state="normal")

    def _open(self) -> None:
        done = [o.result.output for o in self.outcomes if o.result]
        if done:
            open_folder(done[0])


def _convert_into(results: list, paths: list[str], target: str) -> None:
    results.extend(convert_many(paths, target))


def choose(paths: list[str]) -> int:
    root = tk.Tk()
    Chooser(root, paths)
    root.mainloop()
    return 0

