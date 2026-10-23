"""Interface gráfica (tkinter, incluído no Python para Windows)."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from conversor import __version__
from conversor.core import registry
from conversor.core.detect import DetectionError, detect
from conversor.core.engine import ConversionError, convert_file


def common_targets(formats: list[str]) -> list[str]:
    """Destinos disponíveis para TODOS os formatos informados (sem repetir)."""
    if not formats:
        return []
    sets = [set(registry.targets_for(f)) for f in set(formats)]
    return sorted(set.intersection(*sets))


class App(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=10)
        self.master = master
        self.files: dict[str, str] = {}  # id da linha -> caminho
        self.formats: dict[str, str] = {}  # id da linha -> formato detectado
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        master.title(f"Kiuwar Conversor {__version__}")
        master.minsize(720, 480)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self._build()

    # ---------- montagem ----------

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Adicionar arquivos…", command=self.add_dialog).pack(side="left")
        ttk.Button(bar, text="Remover selecionados", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(bar, text="Limpar", command=self.clear).pack(side="left")

        self.tree = ttk.Treeview(self, columns=("fmt", "status"), height=10)
        self.tree.heading("#0", text="Arquivo")
        self.tree.heading("fmt", text="Formato")
        self.tree.heading("status", text="Situação")
        self.tree.column("#0", width=380)
        self.tree.column("fmt", width=80, anchor="center")
        self.tree.column("status", width=220)
        self.tree.grid(row=1, column=0, sticky="nsew", pady=8)

        opts = ttk.Frame(self)
        opts.grid(row=2, column=0, sticky="ew")
        ttk.Label(opts, text="Converter para:").grid(row=0, column=0, sticky="w")
        self.target = tk.StringVar()
        self.target_box = ttk.Combobox(opts, textvariable=self.target, state="readonly", width=10)
        self.target_box.grid(row=0, column=1, sticky="w", padx=6)

        self.same_dir = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts, text="Salvar na mesma pasta do arquivo", variable=self.same_dir,
            command=self._toggle_out_dir,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.out_dir = tk.StringVar()
        self.out_entry = ttk.Entry(opts, textvariable=self.out_dir, width=50, state="disabled")
        self.out_entry.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.out_btn = ttk.Button(opts, text="Escolher pasta…", command=self.pick_out_dir, state="disabled")
        self.out_btn.grid(row=2, column=2, padx=6)

        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Sobrescrever arquivos existentes", variable=self.overwrite
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        run = ttk.Frame(self)
        run.grid(row=3, column=0, sticky="ew", pady=8)
        self.convert_btn = ttk.Button(run, text="Converter", command=self.start)
        self.convert_btn.pack(side="left")
        self.progress = ttk.Progressbar(run, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)

        self.log = tk.Text(self, height=7, state="disabled", wrap="word")
        self.log.grid(row=4, column=0, sticky="nsew")

        ttk.Label(
            self,
            text="Os arquivos são processados apenas neste computador. Nada é enviado à internet.",
            foreground="#555",
        ).grid(row=5, column=0, sticky="w", pady=(6, 0))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)

    # ---------- lista de arquivos ----------

    def add_dialog(self) -> None:
        self.add_files(filedialog.askopenfilenames(title="Escolha os arquivos"))

    def add_files(self, paths) -> None:
        known = set(self.files.values())
        for p in paths:
            p = str(Path(p))
            if p in known:
                continue
            known.add(p)
            try:
                fmt = detect(Path(p)).fmt
                status = "pronto"
            except DetectionError as e:
                fmt, status = "?", str(e)
            iid = self.tree.insert("", "end", text=p, values=(fmt.upper(), status))
            self.files[iid] = p
            if fmt != "?":
                self.formats[iid] = fmt
        self.refresh_targets()

    def remove_selected(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.files.pop(iid, None)
            self.formats.pop(iid, None)
        self.refresh_targets()

    def clear(self) -> None:
        for iid in list(self.files):
            self.tree.delete(iid)
        self.files.clear()
        self.formats.clear()
        self.refresh_targets()

    def refresh_targets(self) -> None:
        targets = common_targets(list(self.formats.values()))
        self.target_box["values"] = [t.upper() for t in targets]
        if self.target.get().lower() not in targets:
            self.target.set(targets[0].upper() if targets else "")

    # ---------- saída ----------

    def _toggle_out_dir(self) -> None:
        state = "disabled" if self.same_dir.get() else "normal"
        self.out_entry.configure(state=state)
        self.out_btn.configure(state=state)

    def pick_out_dir(self) -> None:
        d = filedialog.askdirectory(title="Pasta de saída")
        if d:
            self.out_dir.set(d)

    # ---------- conversão ----------

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        jobs = [(iid, self.files[iid]) for iid in self.files if iid in self.formats]
        target = self.target.get().lower()
        if not jobs or not target:
            messagebox.showinfo("Conversor", "Adicione arquivos válidos e escolha o formato.")
            return
        out_dir = None if self.same_dir.get() else self.out_dir.get().strip()
        if out_dir == "":
            messagebox.showinfo("Conversor", "Escolha a pasta de saída.")
            return
        self.convert_btn.configure(state="disabled")
        self.progress.configure(maximum=len(jobs), value=0)
        args = (jobs, target, out_dir, self.overwrite.get())
        self.worker = threading.Thread(target=self._work, args=args, daemon=True)
        self.worker.start()
        self.after(100, self._poll)

    def _work(self, jobs, target, out_dir, overwrite) -> None:
        # Roda fora da thread da interface; só conversa com ela pela fila.
        for iid, path in jobs:
            self.events.put(("status", iid, "convertendo…"))
            try:
                r = convert_file(path, target, out_dir, overwrite)
                self.events.put(("status", iid, f"ok → {r.output.name}"))
                self.events.put(("log", f"OK  {Path(path).name} → {r.output}"))
                for w in r.warnings:
                    self.events.put(("log", f"AVISO  {w}"))
            except ConversionError as e:
                self.events.put(("status", iid, "erro"))
                self.events.put(("log", f"ERRO  {e}"))
            except Exception as e:  # nunca deixar a thread morrer em silêncio
                self.events.put(("status", iid, "erro inesperado"))
                self.events.put(("log", f"ERRO INESPERADO  {Path(path).name}: {e!r}"))
            self.events.put(("step",))
        self.events.put(("done",))

    def _poll(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "status":
                    self.tree.set(ev[1], "status", ev[2])
                elif ev[0] == "log":
                    self._log(ev[1])
                elif ev[0] == "step":
                    self.progress.step(1)
                elif ev[0] == "done":
                    self.convert_btn.configure(state="normal")
                    return
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def _enable_dpi_awareness() -> None:
    """Evita interface borrada em telas com escala > 100% no Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:  # "Abrir com" / arrastar arquivos sobre o .exe
        app.add_files(sys.argv[1:])
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
