"""Janela de configuração do atalho (Ferramentas → Atalho do painel flutuante…)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox, ttk

from conversor.atalho import config


class JanelaAtalho(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title("Lotus — atalho do painel flutuante")
        self.resizable(False, False)
        cfg = config.carregar()
        g = cfg.gatilho

        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(
            f,
            text="Numa janela do Explorer, use o atalho sobre um arquivo para abrir\n"
                 "um painel com os formatos de conversão.",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ttk.Label(f, text="Teclas:").grid(row=1, column=0, sticky="w")
        self.mods = {m: tk.BooleanVar(value=m in g.modificadores) for m in config.MODIFICADORES}
        mods_frame = ttk.Frame(f)
        mods_frame.grid(row=1, column=1, columnspan=3, sticky="w")
        for m in config.MODIFICADORES:
            ttk.Checkbutton(mods_frame, text=config.NOME_MOD[m], variable=self.mods[m],
                            command=self.atualizar).pack(side="left", padx=4)

        self.tipo = tk.StringVar(value=g.tipo)
        ttk.Radiobutton(f, text="+ botão do mouse:", value="mouse", variable=self.tipo,
                        command=self.atualizar).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.botao = tk.StringVar(value=config.NOME_BOTAO[g.botao])
        self.botao_box = ttk.Combobox(f, textvariable=self.botao, state="readonly", width=28,
                                      values=[config.NOME_BOTAO[b] for b in config.BOTOES])
        self.botao_box.grid(row=2, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.botao_box.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())

        ttk.Radiobutton(f, text="+ tecla:", value="tecla", variable=self.tipo,
                        command=self.atualizar).grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.tecla = tk.StringVar(value=g.tecla)
        self.tecla_box = ttk.Combobox(f, textvariable=self.tecla, state="readonly", width=6,
                                      values=config.TECLAS)
        self.tecla_box.grid(row=3, column=1, sticky="w", pady=(4, 0))
        self.tecla_box.bind("<<ComboboxSelected>>", lambda _e: self.atualizar())
        ttk.Label(f, text="(atua nos arquivos já selecionados)", foreground="#666").grid(
            row=3, column=2, columnspan=2, sticky="w", pady=(4, 0))

        self.ativo = tk.BooleanVar(value=cfg.atalho_ativo)
        ttk.Checkbutton(f, text="Ligar o painel flutuante (e iniciar com o Windows)",
                        variable=self.ativo).grid(row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))

        self.resumo = ttk.Label(f, text="", font=("Segoe UI", 10, "bold"))
        self.resumo.grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.msgs = ttk.Label(f, text="", wraplength=420, justify="left")
        self.msgs.grid(row=6, column=0, columnspan=4, sticky="w")

        bar = ttk.Frame(f)
        bar.grid(row=7, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="Restaurar padrão", command=self.padrao).pack(side="left", padx=4)
        self.salvar_btn = ttk.Button(bar, text="Salvar", command=self.salvar)
        self.salvar_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.atualizar()

    def gatilho(self) -> config.Gatilho:
        nome_para_botao = {v: k for k, v in config.NOME_BOTAO.items()}
        return config.Gatilho(
            modificadores=frozenset(m for m, v in self.mods.items() if v.get()),
            tipo=self.tipo.get(),
            botao=nome_para_botao.get(self.botao.get(), "esquerdo"),
            tecla=self.tecla.get() or "C",
        )

    def atualizar(self) -> None:
        g = self.gatilho()
        erros, avisos = config.validar(g)
        self.botao_box.configure(state="readonly" if g.tipo == "mouse" else "disabled")
        self.tecla_box.configure(state="readonly" if g.tipo == "tecla" else "disabled")
        self.resumo.configure(text=f"Atalho: {g.descrever()}")
        linhas = [f"✗ {e}" for e in erros] + [f"⚠ {a}" for a in avisos]
        self.msgs.configure(text="\n".join(linhas), foreground="#a00" if erros else "#8a5a00")
        self.salvar_btn.configure(state="disabled" if erros else "normal")

    def padrao(self) -> None:
        g = config.PADRAO
        for m, v in self.mods.items():
            v.set(m in g.modificadores)
        self.tipo.set(g.tipo)
        self.botao.set(config.NOME_BOTAO[g.botao])
        self.tecla.set(g.tecla)
        self.atualizar()

    def salvar(self) -> str:
        cfg = config.Config(gatilho=self.gatilho(), atalho_ativo=self.ativo.get())
        config.salvar(cfg)  # o agente em execução percebe a mudança em ~2 s
        msg = f"Atalho salvo: {cfg.gatilho.descrever()}."
        if sys.platform == "win32":
            from conversor.atalho import controle

            try:
                msg = controle.ativar() if cfg.atalho_ativo else controle.desativar()
            except OSError as e:
                messagebox.showerror("Lotus", f"Não foi possível aplicar: {e}", parent=self)
                return msg
        self.destroy()
        return msg
