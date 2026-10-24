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
from conversor.logs import get_logger, registrar_erros_tcl
from conversor.ui.icone import aplicar_icone


def common_targets(formats: list[str]) -> list[str]:
    """Destinos disponíveis para TODOS os formatos informados (sem repetir)."""
    if not formats:
        return []
    sets = [set(registry.targets_for(f)) for f in set(formats)]
    return sorted(set.intersection(*sets))


def situacao_arquivo(fmt: str) -> str:
    """Texto da coluna Situação para um arquivo já detectado."""
    if registry.targets_for(fmt):
        return "pronto"
    nota = _nota_principal(fmt)
    if nota is not None:  # existe conversão, mas falta Word/ffmpeg
        return "indisponível: " + nota.rstrip(".").lower()
    return f"sem conversão para {fmt.upper()}"


def _nota_principal(fmt: str) -> str | None:
    """O requisito que libera mais conversões desse formato (ex.: o Word, e não
    o textutil, que só vale no Mac e só para TXT/HTML)."""
    from collections import Counter

    notas = Counter(c.notes for c in registry.all_converters() if c.source == fmt)
    return notas.most_common(1)[0][0] if notas else None


def motivo_sem_destino(formats: list[str]) -> str | None:
    """Explica por que não há formato de destino; None se há pelo menos um."""
    if not formats:
        return "Adicione arquivos para converter."
    if common_targets(formats):
        return None
    sem = sorted({f for f in formats if not registry.targets_for(f)})
    if sem:
        partes = []
        for f in sem:
            nota = _nota_principal(f)
            if nota is not None:
                partes.append(f"{f.upper()}: {nota.rstrip('.')}")
            else:
                partes.append(f"arquivos {f.upper()} ainda não podem ser convertidos pelo Lotus")
        return "Sem conversão disponível — " + "; ".join(partes) + "."
    nomes = ", ".join(sorted({f.upper() for f in formats}))
    return (f"Os arquivos selecionados ({nomes}) não têm um formato de destino em comum. "
            "Remova alguns e converta cada tipo separadamente.")


class App(ttk.Frame):
    def __init__(self, master: tk.Misc, pal=None, moldura=None):
        from conversor.ui import tema
        from conversor.ui.widgets import aplicar_estilo_ttk

        self.pal = pal or tema.paleta(tema.carregar())
        aplicar_estilo_ttk(master, self.pal)
        super().__init__(master, padding=(16, 8, 16, 12), style="Fundo.TFrame")
        self.master = master
        self.moldura = moldura
        self.files: dict[str, str] = {}  # id da linha -> caminho
        self.formats: dict[str, str] = {}  # id da linha -> formato detectado
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        top = master.winfo_toplevel()
        top.title(f"Lotus {__version__}")
        top.minsize(760, 560)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self._build()

    # ---------- montagem ----------

    def _build(self) -> None:
        from conversor.ui.widgets import BotaoPilula, Cartao

        p = self.pal
        self._build_menubar()

        bar = ttk.Frame(self, style="Fundo.TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        BotaoPilula(bar, "＋  Adicionar arquivos…", command=self.add_dialog, pal=p).pack(side="left")
        BotaoPilula(bar, "Remover selecionados", command=self.remove_selected, pal=p).pack(side="left", padx=8)
        BotaoPilula(bar, "Limpar", command=self.clear, pal=p).pack(side="left")

        lista = Cartao(self, p, pad=6)
        lista.fixar_altura()
        lista.grid(row=1, column=0, sticky="nsew")
        self.tree = ttk.Treeview(lista.interior, columns=("fmt", "status"), height=8)
        self.tree.heading("#0", text="Arquivo", anchor="w")
        self.tree.heading("fmt", text="Formato")
        self.tree.heading("status", text="Situação", anchor="w")
        self.tree.column("#0", width=380)
        self.tree.column("fmt", width=80, anchor="center")
        self.tree.column("status", width=220)
        self.tree.pack(fill="both", expand=True)

        opcoes = Cartao(self, p)
        opcoes.grid(row=2, column=0, sticky="ew", pady=10)
        opts = opcoes.interior
        ttk.Label(opts, text="Converter para").grid(row=0, column=0, sticky="w")
        self.target = tk.StringVar()
        self.target_box = ttk.Combobox(opts, textvariable=self.target, state="readonly", width=10)
        self.target_box.grid(row=0, column=1, sticky="w", padx=8)
        self.hint = ttk.Label(opts, text="", style="Aviso.TLabel", wraplength=440, justify="left")
        self.hint.grid(row=0, column=2, columnspan=2, sticky="w")

        self.same_dir = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts, text="Salvar na mesma pasta do arquivo", variable=self.same_dir,
            command=self._toggle_out_dir,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.out_dir = tk.StringVar()
        self.out_entry = ttk.Entry(opts, textvariable=self.out_dir, width=50, state="disabled")
        self.out_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.out_btn = BotaoPilula(opts, "Escolher pasta…", command=self.pick_out_dir, pal=p,
                                   fundo=p.superficie, altura=28, state="disabled")
        self.out_btn.grid(row=2, column=2, padx=8, pady=(4, 0), sticky="w")

        self.overwrite = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Sobrescrever arquivos existentes", variable=self.overwrite
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        run = ttk.Frame(self, style="Fundo.TFrame")
        run.grid(row=3, column=0, sticky="ew")
        self.convert_btn = BotaoPilula(run, "Converter", command=self.start, pal=p, primario=True,
                                       largura=150, altura=36)
        self.convert_btn.pack(side="left")
        self.progress = ttk.Progressbar(run, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

        registro = Cartao(self, p, pad=8)
        registro.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.log = tk.Text(registro.interior, height=5, state="disabled", wrap="word", bd=0,
                           highlightthickness=0, bg=p.superficie, fg=p.texto, insertbackground=p.texto)
        self.log.pack(fill="both", expand=True)

        ttk.Label(
            self,
            text="Os arquivos são processados apenas neste computador. Nada é enviado à internet.",
            style="Fundo.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(8, 0))

        self.status_painel = None
        self._status_pendente = None
        if sys.platform == "darwin":
            # Indicador do painel por atalho: clicar abre a ativação guiada.
            self.status_painel = ttk.Label(self, text="", style="Fundo.TLabel", cursor="hand2")
            self.status_painel.grid(row=6, column=0, sticky="w", pady=(4, 0))
            self.status_painel.bind("<Button-1>", lambda _e: self.ativar_painel_mac())
            self.bind("<Destroy>", self._parar_status, add="+")
            self._atualizar_status()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

    def _build_menubar(self) -> None:
        tools = tk.Menu(self.master, tearoff=False)
        suportado = "normal" if sys.platform in ("win32", "darwin") else "disabled"
        nome_menu = "Ação Rápida do Finder" if sys.platform == "darwin" else "menu do botão direito"
        tools.add_command(label="Aparência…", command=self.configure_appearance)
        tools.add_command(label="Atalho do painel flutuante…", command=self.configure_hotkey)
        if sys.platform in ("win32", "darwin"):
            from conversor.atalho import config as cfg_atalho

            self.bandeja_var = tk.BooleanVar(value=cfg_atalho.carregar().bandeja)
            rotulo = "Ícone na barra de menus" if sys.platform == "darwin" else "Ícone ao lado do relógio"
            tools.add_checkbutton(label=rotulo, variable=self.bandeja_var, command=self.toggle_tray)
        tools.add_separator()
        tools.add_command(label=f"Instalar {nome_menu}", command=self.install_menu, state=suportado)
        tools.add_command(label=f"Remover {nome_menu}", command=self.uninstall_menu, state=suportado)
        tools.add_separator()
        tools.add_command(label="Diagnosticar e reparar", command=self.diagnose)
        if sys.platform == "darwin":
            tools.add_command(label="Ativar o painel no Mac…", command=self.ativar_painel_mac)
            tools.add_command(label="Diagnóstico do painel flutuante (Mac)…", command=self.diagnose_mac)
        tools.add_command(label="Abrir pasta do log", command=self.open_log_dir)
        tools.add_separator()
        tools.add_command(label="Procurar atualização…", command=self.procurar_atualizacao,
                          state="normal" if sys.platform in ("win32", "darwin") else "disabled")
        tools.add_command(label="Ajuda", command=self.mostrar_ajuda, accelerator="F1")
        self.winfo_toplevel().bind("<F1>", lambda _e: self.mostrar_ajuda(), add="+")
        self.tools_menu = tools
        if self.moldura is not None and self.moldura.propria:
            self.moldura.definir_menu(tools)  # botão "Ferramentas ▾" da barra de título
        else:
            menubar = tk.Menu(self.master)
            menubar.add_cascade(label="Ferramentas", menu=tools)
            self.master.winfo_toplevel().configure(menu=menubar)

    # ---------- ferramentas ----------

    def install_menu(self) -> None:
        if sys.platform == "darwin":
            from conversor import acao_rapida

            acao_rapida.instalar()
            self._log("Ação Rápida instalada: no Finder, clique direito → Ações Rápidas → Converter com Lotus.")
            return
        from conversor import shell

        try:
            n = shell.install()
        except OSError as e:
            messagebox.showerror("Lotus", f"Não foi possível gravar no registro: {e}")
            return
        self._log(f"Menu \"Converter para\" instalado em {n} tipos de arquivo "
                  "(no Windows 11: \"Mostrar mais opções\").")

    def uninstall_menu(self) -> None:
        if sys.platform == "darwin":
            from conversor import acao_rapida

            acao_rapida.desinstalar()
            self._log("Ação Rápida removida.")
            return
        from conversor import shell

        self._log(f"Menu removido de {shell.uninstall()} tipos de arquivo.")

    def toggle_tray(self) -> None:
        from conversor.atalho import controle

        ligar = self.bandeja_var.get()
        self._log(controle.ativar_bandeja() if ligar else controle.desativar_bandeja())

    def configure_appearance(self) -> None:
        from conversor.ui.janela_aparencia import JanelaAparencia

        JanelaAparencia(self.master.winfo_toplevel())

    def configure_hotkey(self) -> None:
        from conversor.atalho.janela_config import JanelaAtalho

        JanelaAtalho(self.master)

    def diagnose(self) -> None:
        from conversor import diagnostics

        for line in diagnostics.run():
            self._log(line)

    # ---------- painel por atalho no Mac ----------

    STATUS_MS = 3000
    _CORES_STATUS = {"ok": "#1E8E3E", "aviso": "#B25E00", "desligado": "#6E6E73"}

    def _atualizar_status(self) -> None:
        self._status_pendente = None
        from conversor.atalho import ativacao_mac

        try:
            texto, nivel = ativacao_mac.resumo(ativacao_mac.coletar_estado())
        except Exception:  # noqa: BLE001 - o indicador nunca derruba a janela
            get_logger().exception("status do painel")
            texto, nivel = "Painel por atalho: estado desconhecido — clique para ver", "aviso"
        self.status_painel.configure(text=texto, foreground=self._CORES_STATUS[nivel])
        self._status_pendente = self.after(self.STATUS_MS, self._atualizar_status)

    def _parar_status(self, evento) -> None:
        if evento.widget is self and self._status_pendente is not None:
            try:
                self.after_cancel(self._status_pendente)
            except tk.TclError:
                pass
            self._status_pendente = None

    def ativar_painel_mac(self, ao_fechar=None):
        from conversor.atalho import janela_ativacao

        janela = getattr(self, "_guia", None)
        if janela is not None and not janela.fechado:
            janela.lift()
            return janela
        self._guia = janela_ativacao.abrir(self.winfo_toplevel(), ao_fechar=ao_fechar)
        return self._guia

    def mostrar_ajuda(self):
        from conversor.ui import janela_ajuda

        janela = getattr(self, "_ajuda", None)
        if janela is not None and janela.winfo_exists():
            janela.lift()
            return janela
        acoes = {"Diagnosticar e reparar": self.diagnose, "Abrir pasta do log": self.open_log_dir}
        if sys.platform == "darwin":
            acoes["Ativar o painel no Mac…"] = self.ativar_painel_mac
        self._ajuda = janela_ajuda.abrir(self.winfo_toplevel(), acoes=acoes)
        return self._ajuda

    def procurar_atualizacao(self, ja_autorizado: bool = False):
        from conversor.ui import janela_atualizacao

        janela = getattr(self, "_atualizacao", None)
        if janela is not None and not janela.fechado:
            janela.lift()
            return janela
        topo = self.winfo_toplevel()
        self._atualizacao = janela_atualizacao.abrir(topo, ao_reiniciar=topo.destroy,
                                                     ja_autorizado=ja_autorizado)
        return self._atualizacao

    def diagnose_mac(self) -> None:
        """Roda em thread (o osascript pode esperar a pergunta de permissão do
        macOS); a thread só devolve texto pela fila (regra 11)."""
        fila: queue.Queue = queue.Queue()
        self._log("Diagnóstico do painel no Mac: verificando (pode aparecer um pedido de permissão)…")
        threading.Thread(target=_diagnostico_mac, args=(fila,), daemon=True).start()
        self.after(200, self._poll_diag, fila)

    def _poll_diag(self, fila: queue.Queue) -> None:
        try:
            texto = fila.get_nowait()
        except queue.Empty:
            self.after(200, self._poll_diag, fila)
            return
        for linha in texto.splitlines():
            self._log(linha)
        messagebox.showinfo("Lotus — diagnóstico do painel", texto, parent=self)

    def open_log_dir(self) -> None:
        from conversor.logs import log_dir
        from conversor.menu import open_dir

        log_dir().mkdir(parents=True, exist_ok=True)
        open_dir(log_dir())

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
                status = situacao_arquivo(fmt)
            except DetectionError as e:
                fmt, status = "?", str(e)
            iid = self.tree.insert("", "end", text=Path(p).name, values=(fmt.upper(), status))
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
        motivo = motivo_sem_destino(list(self.formats.values())) if self.files else None
        self.hint.configure(text=motivo or "")

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
            if self.files and not jobs:
                motivo = "Nenhum dos arquivos foi reconhecido (veja a coluna Situação)."
            else:
                motivo = motivo_sem_destino(list(self.formats.values())) or "Escolha o formato."
            messagebox.showinfo("Lotus", motivo)
            return
        out_dir = None if self.same_dir.get() else self.out_dir.get().strip()
        if out_dir == "":
            messagebox.showinfo("Lotus", "Escolha a pasta de saída.")
            return
        self.convert_btn.configure(state="disabled")
        self.progress.configure(maximum=len(jobs), value=0)
        # A thread recebe só dados e a fila, nunca `self`: se ela segurasse um
        # objeto do tkinter, o coletor de lixo poderia destruí-lo fora da
        # thread principal e derrubar o Tcl ("Tcl_AsyncDelete").
        args = (self.events, jobs, target, out_dir, self.overwrite.get())
        self.worker = threading.Thread(target=_work, args=args, daemon=True)
        self.worker.start()
        self.after(100, self._poll)

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


def _lembrete_mensal(root: tk.Tk, app: App) -> None:
    """Uma vez por mês só PERGUNTA se a pessoa quer procurar atualização; a
    internet só é usada se ela disser sim."""
    from conversor import atualizar

    try:
        if not atualizar.deve_lembrar():
            return
    except Exception:  # noqa: BLE001 - o lembrete nunca impede o app de abrir
        get_logger().exception("lembrete de atualização")
        return
    sim = messagebox.askyesno(
        "Lotus — atualizações",
        "Já faz um mês. Quer procurar uma versão nova do Lotus agora?\n\n"
        "Para isso o Lotus acessa o GitHub (github.com); nenhum dado seu é enviado. "
        "Você também pode procurar quando quiser em Ferramentas → Procurar atualização.",
        parent=root)
    atualizar.lembrete_respondido()
    if sim:
        app.procurar_atualizacao(ja_autorizado=True)


def _preparar_mac() -> None:
    """Mac, em thread (só dados; regra 11): na 1ª abertura instala a Ação Rápida
    (funciona sem permissões); sempre, liga o agente se o ícone da barra de menus
    ou o painel estiver ligado (inclusive depois de uma atualização)."""
    from conversor import acao_rapida
    from conversor.atalho import config, controle

    log = get_logger()
    cfg = config.carregar()
    if not cfg.guia_mac_visto:
        try:
            if not acao_rapida.instalada():
                acao_rapida.instalar()
                log.info("Ação Rápida instalada na 1ª abertura")
        except Exception:  # noqa: BLE001
            log.exception("instalar a Ação Rápida na 1ª abertura")
    try:
        if controle.precisa_rodar(cfg) and not controle.agente_rodando():
            controle.ativar_inicio()
            controle.iniciar_agente()
    except Exception:  # noqa: BLE001
        log.exception("ligar o agente do Mac")


def _guia_na_primeira_vez(root: tk.Tk, app: App) -> None:
    """Mac: na 1ª abertura, a janela "Ativar o Lotus no Mac" (o painel vem desligado)."""
    from conversor.atalho import config

    threading.Thread(target=_preparar_mac, daemon=True).start()
    cfg = config.carregar()
    if cfg.guia_mac_visto:
        return

    def visto() -> None:
        c = config.carregar()
        c.guia_mac_visto = True
        config.salvar(c)

    root.after(600, lambda: app.ativar_painel_mac(ao_fechar=visto))


def _diagnostico_mac(fila: queue.Queue) -> None:
    from conversor.atalho import diagnostico_mac

    try:
        fila.put(diagnostico_mac.executar())
    except Exception as e:  # noqa: BLE001 - o diagnóstico nunca pode derrubar a janela
        get_logger().exception("diagnóstico do Mac")
        fila.put(f"O diagnóstico falhou: {e}. Detalhes no log.")


def _work(events: queue.Queue, jobs, target, out_dir, overwrite) -> None:
    # Roda fora da thread da interface; só conversa com ela pela fila.
    for iid, path in jobs:
        events.put(("status", iid, "convertendo…"))
        try:
            r = convert_file(path, target, out_dir, overwrite)
            events.put(("status", iid, f"ok → {r.output.name}"))
            events.put(("log", f"OK  {Path(path).name} → {r.output}"))
            for w in r.warnings:
                events.put(("log", f"AVISO  {w}"))
        except ConversionError as e:
            events.put(("status", iid, "erro"))
            events.put(("log", f"ERRO  {e}"))
        except Exception as e:  # nunca deixar a thread morrer em silêncio
            events.put(("status", iid, "erro inesperado"))
            events.put(("log", f"ERRO INESPERADO  {Path(path).name}: {e!r}"))
        events.put(("step",))
    events.put(("done",))


def _enable_dpi_awareness() -> None:
    """Evita interface borrada em telas com escala > 100% no Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    from conversor.ui import tema
    from conversor.ui.moldura import Moldura, centralizar

    files = sys.argv[1:] if argv is None else argv
    _enable_dpi_awareness()
    root = tk.Tk()
    registrar_erros_tcl(root)
    aplicar_icone(root)
    aparencia = tema.carregar()
    pal = tema.paleta(aparencia)
    propria = sys.platform == "win32" and not aparencia.moldura_windows
    moldura = Moldura(root, pal, f"Lotus {__version__}", propria=propria)
    centralizar(root, 860, 680)
    app = App(moldura.conteudo, pal=pal, moldura=moldura)
    if files:  # "Abrir com" / arrastar arquivos sobre o .exe
        app.add_files(files)
    if sys.platform in ("win32", "darwin"):
        root.after(1500, lambda: _lembrete_mensal(root, app))
    if sys.platform == "darwin":
        # No Mac, arquivos enviados pelo Finder chegam como evento do Tk.
        root.createcommand("::tk::mac::OpenDocument", lambda *caminhos: app.add_files(caminhos))
        _guia_na_primeira_vez(root, app)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
