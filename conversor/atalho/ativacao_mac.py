"""Ativação guiada do painel por atalho no Mac (3 passos), lógica pura.

1. Ligar o painel (vem desligado após instalar).
2. Permitir Acessibilidade (sem ela o macOS não entrega os cliques).
3. Permitir que o Lotus leia a seleção do Finder (Automação).

A janela (janela_ativacao.py) só desenha o que `passos()` devolve e repete a
consulta a cada segundo; quando um passo fica pronto, ele muda sozinho.

Endereços dos Ajustes do Sistema: a Apple não os documenta. Usamos os da
lista mantida pela comunidade (github.com/bvanpeski/SystemPreferences,
macos_preferencepanes-Ventura.md):
    x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility
    x-apple.systempreferences:com.apple.preference.security?Privacy_Automation
Se o `open` falhar, abrimos a página geral de Privacidade e Segurança
(com.apple.settings.PrivacySecurity.extension, mesma lista) e o caminho
também aparece escrito na janela. Abrir a seção certa é teste manual.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

URL_ACESSIBILIDADE = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
URL_AUTOMACAO = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
URL_PRIVACIDADE = "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension"
URLS = {"acessibilidade": URL_ACESSIBILIDADE, "automacao": URL_AUTOMACAO}

# Depois de abrir os Ajustes, quanto esperar até sugerir "remover (−) e adicionar (+)".
ESPERA_PERMISSAO_VELHA = 20.0


@dataclass
class Passo:
    numero: int
    titulo: str
    feito: bool
    explicacao: str
    botao: str = ""        # rótulo do botão ("" = sem botão)
    acao: str = ""         # "ligar" | "acessibilidade" | "testar_finder" | "automacao"
    dica: str = ""         # ajuda extra (ex.: permissão de versão anterior)


def passos(e: dict) -> list[Passo]:
    """e: atalho_ativo, agente_rodando, ax_confiavel, estado_agente, automacao,
    assinatura, segundos_desde_ajustes (None se o usuário não abriu os Ajustes)."""
    ligado = bool(e.get("atalho_ativo")) and bool(e.get("agente_rodando"))
    p1 = Passo(1, "Ligar o painel por atalho", ligado,
               "O painel vem desligado. Ao ligar, o Lotus fica em segundo plano e volta "
               "sozinho quando o Mac reinicia." if not ligado else
               f"Ligado: {e.get('gatilho', '⌥ Option + ⇧ Shift + clique')} no Finder ou na Mesa.",
               "" if ligado else "Ligar agora", "" if ligado else "ligar")

    agente = e.get("estado_agente") or {}
    ax = e.get("ax_confiavel")
    gancho_ok = bool(agente.get("gancho_ok"))
    feito2 = ax is True and (gancho_ok or not ligado)
    if feito2:
        expl2 = "Permitido: o macOS entrega ao Lotus os cliques com o atalho."
    elif ax is True and ligado:
        expl2 = ("Permissão dada. O Lotus está ativando o atalho (leva alguns segundos)…")
    else:
        expl2 = ("Em Ajustes do Sistema → Privacidade e Segurança → Acessibilidade, ative "
                 "\"Lotus\". Esta janela atualiza sozinha quando a permissão chegar.")
    dica2 = ""
    espera = e.get("segundos_desde_ajustes")
    if ax is False and espera is not None and espera >= ESPERA_PERMISSAO_VELHA:
        dica2 = ("Já está ativado lá e aqui continua pendente? A permissão é de uma versão "
                 "anterior do Lotus. Em Acessibilidade, selecione Lotus, clique em − (remover), "
                 "depois em + e escolha /Applications/Lotus.app.")
    p2 = Passo(2, "Permitir Acessibilidade", feito2, expl2,
               "" if feito2 else "Abrir Acessibilidade", "" if feito2 else "acessibilidade", dica2)

    auto = e.get("automacao")
    if auto == "ok":
        p3 = Passo(3, "Permitir ler a seleção do Finder", True,
                   "Permitido: o Lotus sabe quais arquivos você clicou.")
    elif auto == "negado":
        p3 = Passo(3, "Permitir ler a seleção do Finder", False,
                   "O macOS bloqueou. Em Privacidade e Segurança → Automação → Lotus, marque "
                   "\"Finder\".", "Abrir Automação", "automacao")
    elif auto == "testando":
        p3 = Passo(3, "Permitir ler a seleção do Finder", False,
                   "Se o Mac perguntar se o Lotus pode controlar o \"Finder\", clique em Permitir.")
    else:
        p3 = Passo(3, "Permitir ler a seleção do Finder", False,
                   "O Mac vai perguntar se o Lotus pode controlar o \"Finder\": clique em Permitir. "
                   "O Lotus só lê quais arquivos estão selecionados.",
                   "Testar o Finder", "testar_finder")
    return [p1, p2, p3]


def tudo_pronto(lista: list[Passo]) -> bool:
    return all(p.feito for p in lista)


def resumo(e: dict) -> tuple[str, str]:
    """(texto curto, nível) para o indicador da janela principal: nível ∈ ok, aviso, desligado."""
    if not e.get("atalho_ativo"):
        return "Painel por atalho: desligado — clique para ativar", "desligado"
    lista = passos(e)
    pendentes = [p for p in lista if not p.feito]
    if not pendentes:
        return "Painel por atalho: pronto ✓", "ok"
    return f"Painel por atalho: falta {pendentes[0].titulo.lower()} — clique para ver", "aviso"


def abrir_ajustes(qual: str, executar=subprocess.run) -> bool:
    """Abre a seção dos Ajustes do Sistema. True se o `open` aceitou o endereço."""
    for url in (URLS[qual], URL_PRIVACIDADE):
        try:
            r = executar(["open", url], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            return True
    return False


def coletar_estado(automacao: str | None = None) -> dict:
    """Leitura rápida (sem osascript) para a janela atualizar a cada segundo."""
    from conversor.atalho import config, mac

    cfg = config.carregar()
    return {
        "atalho_ativo": cfg.atalho_ativo,
        "gatilho": cfg.gatilho.descrever(),
        "agente_rodando": mac.agente_rodando(),
        "ax_confiavel": mac.ax_confiavel(),
        "estado_agente": mac.ler_estado_agente(),
        "automacao": automacao,
    }
