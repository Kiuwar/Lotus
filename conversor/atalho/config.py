"""Configuração do atalho do painel flutuante (ex.: Ctrl+Shift+clique).

Gravada em %APPDATA%\\Lotus\\config.json. Arquivo ausente ou corrompido não
derruba o app: volta ao padrão, e o corrompido é guardado para análise.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from conversor.logs import get_logger

MODIFICADORES = ("ctrl", "shift", "alt", "win")
MAC = sys.platform == "darwin"
# No Mac: "alt" é a tecla ⌥ Option e "win" é a ⌘ Command.
NOME_MOD = ({"ctrl": "⌃ Control", "shift": "⇧ Shift", "alt": "⌥ Option", "win": "⌘ Cmd"} if MAC
            else {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "win": "Win"})
_LISTA_MODS = ", ".join(NOME_MOD[m] for m in ("ctrl", "shift", "alt", "win"))

# Padrão: Ctrl+Shift no Windows; Option+Shift no Mac (Cmd+clique já é
# "selecionar vários" no Finder, assim como Ctrl+clique no Explorer).
MODS_PADRAO = frozenset({"alt", "shift"}) if MAC else frozenset({"ctrl", "shift"})

BOTOES = ("esquerdo", "direito", "meio", "lateral1", "lateral2")
NOME_BOTAO = {
    "esquerdo": "clique esquerdo",
    "direito": "clique direito",
    "meio": "clique do meio (roda)",
    "lateral1": "botão lateral 1 (voltar)",
    "lateral2": "botão lateral 2 (avançar)",
}

TECLAS = (
    [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [str(d) for d in range(10)]
    + [f"F{n}" for n in range(1, 25)]
)


def vk_da_tecla(tecla: str) -> int:
    """Código virtual do Windows (VK_*) para as teclas aceitas."""
    if len(tecla) == 1 and (tecla.isdigit() or "A" <= tecla <= "Z"):
        return ord(tecla)  # VK de letras e dígitos = código ASCII maiúsculo
    if tecla.startswith("F") and tecla[1:].isdigit() and 1 <= int(tecla[1:]) <= 24:
        return 0x70 + int(tecla[1:]) - 1  # VK_F1 = 0x70
    raise ValueError(f"tecla não suportada: {tecla}")


@dataclass(frozen=True)
class Gatilho:
    modificadores: frozenset = field(default_factory=lambda: MODS_PADRAO)
    tipo: str = "mouse"  # "mouse" ou "tecla"
    botao: str = "esquerdo"
    tecla: str = "C"

    def descrever(self) -> str:
        mods = "+".join(NOME_MOD[m] for m in MODIFICADORES if m in self.modificadores)
        alvo = NOME_BOTAO[self.botao] if self.tipo == "mouse" else self.tecla
        return f"{mods}+{alvo}" if mods else alvo

    def para_dict(self) -> dict:
        return {
            "modificadores": [m for m in MODIFICADORES if m in self.modificadores],
            "tipo": self.tipo,
            "botao": self.botao,
            "tecla": self.tecla,
        }

    @classmethod
    def de_dict(cls, d: dict) -> "Gatilho":
        mods = d.get("modificadores", sorted(MODS_PADRAO))
        if not isinstance(mods, list):
            raise ValueError("modificadores deve ser uma lista")
        return cls(
            modificadores=frozenset(str(m) for m in mods),
            tipo=str(d.get("tipo", "mouse")),
            botao=str(d.get("botao", "esquerdo")),
            tecla=str(d.get("tecla", "C")).upper(),
        )


PADRAO = Gatilho()


def validar(g: Gatilho) -> tuple[list[str], list[str]]:
    """(erros que impedem salvar, avisos)."""
    erros, avisos = [], []
    desconhecidos = set(g.modificadores) - set(MODIFICADORES)
    if desconhecidos:
        erros.append(f"Modificador desconhecido: {', '.join(sorted(desconhecidos))}.")
    if g.tipo not in ("mouse", "tecla"):
        erros.append(f"Tipo de atalho desconhecido: {g.tipo}.")
        return erros, avisos

    if g.tipo == "mouse":
        if g.botao not in BOTOES:
            erros.append(f"Botão desconhecido: {g.botao}.")
        elif not g.modificadores and g.botao in ("esquerdo", "direito"):
            erros.append(
                "Clique esquerdo ou direito sem tecla modificadora bloquearia o uso normal "
                f"do mouse. Marque ao menos uma tecla ({_LISTA_MODS})."
            )
        selecao_multipla = ({"win"}, {"shift"}) if MAC else ({"ctrl"}, {"shift"})
        if g.botao == "esquerdo" and g.modificadores in selecao_multipla:
            avisos.append(
                f"No {'Finder' if MAC else 'Explorer'}, "
                f"{'⌘ Cmd' if MAC else 'Ctrl'}+clique e Shift+clique já servem para selecionar "
                "vários arquivos. Com este atalho, essa função deixa de funcionar."
            )
        if MAC and g.botao == "esquerdo" and g.modificadores == {"ctrl"}:
            avisos.append("No Mac, ⌃ Control+clique abre o menu de contexto; ele deixará de abrir.")
        if not MAC and g.botao == "direito" and not (g.modificadores - {"shift"}):
            avisos.append("Shift+clique direito abre o menu estendido do Windows; ele deixará de abrir.")
    else:
        try:
            vk_da_tecla(g.tecla)
        except ValueError:
            erros.append(f"Tecla não suportada: {g.tecla}. Use A–Z, 0–9 ou F1–F24.")
        else:
            if not g.modificadores and not g.tecla.startswith("F"):
                erros.append(
                    "Letra ou número sem tecla modificadora impediria digitar essa tecla. "
                    f"Marque ao menos uma tecla ({_LISTA_MODS})."
                )
            comum = {"win"} if MAC else {"ctrl"}
            if g.modificadores == comum and g.tecla in {"A", "C", "V", "X", "Z", "Y", "S"}:
                avisos.append(f"{NOME_MOD[next(iter(comum))]}+{g.tecla} é um atalho comum do sistema "
                              "e deixará de funcionar.")

    if "win" in g.modificadores and not MAC:
        avisos.append("Atalhos com Win podem estar reservados pelo Windows e não funcionar.")
    return erros, avisos


# ---------- arquivo ----------

def pasta_config() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "Lotus"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Lotus"
    return Path.home() / ".lotus"


def arquivo_config() -> Path:
    return pasta_config() / "config.json"


@dataclass
class Config:
    gatilho: Gatilho = PADRAO
    atalho_ativo: bool = False
    # Ícone ao lado do relógio (Windows) ou na barra de menus (Mac). Ligado por padrão.
    bandeja: bool = True
    # Mac: a janela "Ativar o painel" já foi mostrada na 1ª abertura.
    guia_mac_visto: bool = False


def carregar(caminho: Path | None = None) -> Config:
    caminho = caminho or arquivo_config()
    if not caminho.is_file():
        return Config()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        g = Gatilho.de_dict(dados.get("atalho", {}))
        erros, _ = validar(g)
        if erros:
            raise ValueError("; ".join(erros))
        return Config(gatilho=g, atalho_ativo=bool(dados.get("atalho_ativo", False)),
                      bandeja=bool(dados.get("bandeja", True)),
                      guia_mac_visto=bool(dados.get("guia_mac_visto", False)))
    except Exception as e:
        # Reparo: guarda o arquivo ruim e segue com o padrão.
        reserva = caminho.with_suffix(".json.corrompido")
        try:
            os.replace(caminho, reserva)
        except OSError:
            pass
        get_logger().warning("config inválida (%s); usando o padrão. Cópia em %s", e, reserva)
        return Config()


def salvar(cfg: Config, caminho: Path | None = None) -> None:
    erros, _ = validar(cfg.gatilho)
    if erros:
        raise ValueError("; ".join(erros))
    caminho = caminho or arquivo_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"versao": 1, "atalho": cfg.gatilho.para_dict(), "atalho_ativo": cfg.atalho_ativo,
             "bandeja": cfg.bandeja, "guia_mac_visto": cfg.guia_mac_visto},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, caminho)
