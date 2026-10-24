"""Diagnóstico do painel por atalho no Mac ("nada acontece").

Não conserta nada: só mostra, item por item, o que está certo (✓), o que
impede o painel de abrir (✕) e o que merece atenção (⚠), cada um com
"Como resolver". Duas partes:

- `coletar()` (só no Mac): lê a configuração, o agente, a permissão de
  Acessibilidade (AXIsProcessTrusted), a de Automação do Finder (osascript
  inofensivo; -1743 = negada), onde o app está e como foi assinado, e o
  relatório que o próprio agente grava ao iniciar (estado-agente.json).
- `avaliar(fatos)` (lógica pura, testada em qualquer sistema): transforma os
  fatos em itens.

Sem rede: tudo é local (regra 8).
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import subprocess
import sys
from dataclasses import dataclass

from conversor.logs import get_logger, log_file

OK, ERRO, ATENCAO = "✓", "✕", "⚠"

CAMINHO_ACESSIBILIDADE = "Ajustes do Sistema → Privacidade e Segurança → Acessibilidade"
CAMINHO_AUTOMACAO = "Ajustes do Sistema → Privacidade e Segurança → Automação → Lotus"
LIGAR_PAINEL = ("Abra o Lotus → Ferramentas → Atalho do painel flutuante… → marque "
                "\"Ligar o painel flutuante\" e clique em Salvar.")


@dataclass
class Item:
    simbolo: str
    titulo: str
    como_resolver: str = ""

    def texto(self) -> str:
        linha = f"{self.simbolo} {self.titulo}"
        return linha + (f"\n    Como resolver: {self.como_resolver}" if self.como_resolver else "")


def avaliar(f: dict) -> list[Item]:
    itens: list[Item] = []
    ativo = f.get("atalho_ativo", False)

    # 1. O painel está ligado? (no Mac vem desligado após instalar)
    if ativo:
        itens.append(Item(OK, f"Painel por atalho ligado ({f.get('gatilho', '?')})."))
    else:
        itens.append(Item(ERRO, "O painel por atalho está DESLIGADO (é assim logo após instalar).",
                          LIGAR_PAINEL))

    if f.get("gatilho_tipo") == "tecla":
        itens.append(Item(ERRO, "O atalho está configurado como TECLA, mas no Mac o painel só "
                          "funciona com clique.",
                          "Ferramentas → Atalho do painel flutuante… → escolha \"+ botão do "
                          "mouse\" e Salvar."))

    # 2. O agente (processo em segundo plano) está rodando?
    if f.get("agente_rodando"):
        itens.append(Item(OK, "Agente do Lotus rodando em segundo plano."))
    elif ativo:
        itens.append(Item(ERRO, "O painel está ligado, mas o agente não está rodando.",
                          "Desligue e ligue de novo o painel (Ferramentas → Atalho do painel "
                          "flutuante…). Se continuar, veja o log indicado no fim."))
    else:
        itens.append(Item(ATENCAO, "Agente parado (normal enquanto o painel estiver desligado)."))

    # 3. Início automático (LaunchAgent)
    registrado, esperado = f.get("inicio_registrado"), f.get("inicio_esperado")
    if ativo and not registrado:
        itens.append(Item(ERRO, "O início automático (LaunchAgent) não está registrado.", LIGAR_PAINEL))
    elif registrado and esperado and registrado != esperado:
        itens.append(Item(ERRO, f"O início automático aponta para outro lugar: {registrado}",
                          "O Lotus foi movido depois de ligar o painel. " + LIGAR_PAINEL))
    elif registrado:
        itens.append(Item(OK, "Início automático registrado para este Lotus."))

    # 4. Acessibilidade (sem ela o macOS não entrega os cliques ao Lotus)
    ax = f.get("ax_confiavel")
    adhoc = f.get("assinatura") == "adhoc"
    quem = ("Este teste rodou pelo Terminal: o resultado vale para o Terminal, não para o Lotus. "
            if f.get("processo") == "terminal" else "")
    reconceder = (f"Se o Lotus JÁ aparece ativado em {CAMINHO_ACESSIBILIDADE}, a permissão é de "
                  "uma versão anterior (cada versão do Lotus tem uma assinatura nova): selecione "
                  "Lotus, clique em − (remover), depois em + e escolha /Applications/Lotus.app.")
    if ax is True:
        itens.append(Item(OK, "Permissão de Acessibilidade concedida."))
    elif ax is False:
        itens.append(Item(ERRO, quem + "Sem permissão de Acessibilidade: o macOS não entrega os "
                          "cliques ao Lotus.",
                          f"{CAMINHO_ACESSIBILIDADE} → ative \"Lotus\". " + (reconceder if adhoc else "")))
    else:
        itens.append(Item(ATENCAO, "Não foi possível consultar a permissão de Acessibilidade."))

    # 5. O que o próprio agente relatou ao iniciar (gancho criado ou não)
    est = f.get("estado_agente")
    if est is None:
        if f.get("agente_rodando"):
            itens.append(Item(ATENCAO, "O agente em execução não deixou relatório (versão anterior "
                              "do Lotus ainda rodando).", "Desligue e ligue de novo o painel."))
    elif est.get("gancho_ok"):
        itens.append(Item(OK, f"O agente instalou o gancho de cliques às {est.get('inicio', '?')}."))
    else:
        erro = est.get("erro") or "motivo desconhecido"
        if ax is True and est.get("ax_confiavel") is False:
            itens.append(Item(ERRO, "A permissão foi dada DEPOIS que o agente começou, e ele não "
                              f"tenta de novo sozinho (agente iniciado às {est.get('inicio', '?')}).",
                              "Desligue e ligue de novo o painel (ou saia da sessão e entre de novo)."))
        else:
            itens.append(Item(ERRO, f"O agente NÃO conseguiu instalar o gancho de cliques: {erro}",
                              f"{CAMINHO_ACESSIBILIDADE} → ative \"Lotus\"; depois desligue e ligue o "
                              "painel. " + (reconceder if adhoc else "")))

    # 6. Automação do Finder (para ler os arquivos selecionados)
    auto = f.get("automacao")
    if auto == "ok":
        itens.append(Item(OK, "Permissão de Automação do Finder concedida."))
    elif auto == "negado":
        itens.append(Item(ERRO, "O macOS bloqueou o Lotus de ler a seleção do Finder (erro -1743).",
                          f"{CAMINHO_AUTOMACAO} → marque \"Finder\"."))
    elif auto == "sem_resposta":
        itens.append(Item(ATENCAO, "O Finder não respondeu a tempo (o macOS pode estar mostrando "
                          "a pergunta de permissão).", "Responda \"Permitir\" e rode o diagnóstico de novo."))
    elif auto:
        itens.append(Item(ATENCAO, f"Não foi possível testar a Automação do Finder: {auto}"))

    # 7. Onde o app está
    caminho = f.get("caminho_app") or ""
    if "/AppTranslocation/" in caminho:
        itens.append(Item(ERRO, "O macOS está rodando uma cópia isolada do Lotus (App Translocation); "
                          "permissões dadas a essa cópia se perdem.",
                          "Arraste o Lotus para a pasta Aplicativos e abra de lá."))
    elif caminho.startswith("/Volumes/"):
        itens.append(Item(ERRO, f"O Lotus está rodando de dentro do disco .dmg ({caminho}).",
                          "Arraste o Lotus para a pasta Aplicativos, ejete o .dmg e abra de lá."))
    elif "/Downloads/" in caminho:
        itens.append(Item(ATENCAO, f"O Lotus está na pasta Downloads ({caminho}).",
                          "Mova para a pasta Aplicativos e ligue o painel de novo."))
    elif caminho:
        itens.append(Item(OK, f"Local do app: {caminho}"))
    if adhoc:
        itens.append(Item(ATENCAO, "Assinatura ad-hoc (sem conta paga da Apple): ao atualizar o "
                          "Lotus, o macOS pode manter a permissão antiga, que não vale mais.",
                          reconceder))

    # 8. Onde ver os detalhes
    itens.append(Item(ATENCAO if any(i.simbolo == ERRO for i in itens) else OK,
                      f"Log com detalhes: {f.get('log', log_file())}"))
    return itens


def texto(itens: list[Item], fatos: dict) -> str:
    cab = (f"Diagnóstico do painel no Mac — {fatos.get('quando', '')} — macOS "
           f"{fatos.get('macos', '?')}, Lotus {fatos.get('versao', '?')}")
    problemas = sum(i.simbolo == ERRO for i in itens)
    resumo = ("Nenhum problema encontrado." if not problemas
              else f"{problemas} problema(s) impedem o painel de abrir; resolva de cima para baixo.")
    return "\n".join([cab, resumo, ""] + [i.texto() for i in itens])


# ---------- coleta (só no Mac) ----------

SCRIPT_AUTOMACAO = 'tell application "Finder" to count (get selection)'


def testar_automacao(executar=subprocess.run, limite: float = 30) -> str:
    """Pergunta algo inofensivo ao Finder. Na 1ª vez o macOS mostra o pedido
    de permissão de Automação; depois responde direto."""
    try:
        r = executar(["osascript", "-e", SCRIPT_AUTOMACAO], capture_output=True, text=True,
                     timeout=limite)
    except subprocess.TimeoutExpired:
        return "sem_resposta"
    except OSError as e:
        return f"osascript indisponível ({e})"
    if r.returncode == 0:
        return "ok"
    erro = (r.stderr or "").strip()
    return "negado" if "-1743" in erro else (erro or f"código {r.returncode}")


def _pacote_app(caminho: str) -> str:
    i = caminho.find(".app/")
    return caminho[: i + 4] if i >= 0 else caminho


def assinatura(pacote: str, executar=subprocess.run) -> str:
    try:
        r = executar(["codesign", "-dv", pacote], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "desconhecida"
    saida = (r.stderr or "") + (r.stdout or "")
    if "Signature=adhoc" in saida:
        return "adhoc"
    if "Authority=" in saida:
        return "desenvolvedor"
    return "sem assinatura" if "not signed" in saida else "desconhecida"


def coletar() -> dict:
    from conversor import __version__, shell
    from conversor.atalho import config, controle, mac

    cfg = config.carregar()
    executavel = shell.launcher_command()[0]
    fatos = {
        "quando": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "macos": platform.mac_ver()[0] or "?",
        "versao": __version__,
        "atalho_ativo": cfg.atalho_ativo,
        "gatilho": cfg.gatilho.descrever(),
        "gatilho_tipo": cfg.gatilho.tipo,
        "agente_rodando": mac.agente_rodando(),
        "inicio_registrado": controle.inicio_registrado(),
        "inicio_esperado": controle.comando_agente(),
        "ax_confiavel": mac.ax_confiavel(),
        "estado_agente": mac.ler_estado_agente(),
        "automacao": testar_automacao(),
        "caminho_app": _pacote_app(executavel),
        "assinatura": assinatura(_pacote_app(executavel)),
        "processo": "app" if ".app/Contents/MacOS/" in sys.executable else "terminal",
        "log": str(log_file()),
    }
    return fatos


def executar() -> str:
    """Coleta, avalia, grava no log e devolve o texto para mostrar."""
    fatos = coletar()
    saida = texto(avaliar(fatos), fatos)
    get_logger().info("diagnóstico do Mac:\n%s\nfatos: %s", saida,
                      json.dumps(fatos, ensure_ascii=False, default=str))
    return saida
