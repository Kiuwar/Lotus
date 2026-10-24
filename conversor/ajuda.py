"""Conteúdo da Ajuda (Ferramentas → Ajuda, ou F1). Só texto: funciona sem internet.

Cada seção é (título, [(tipo, texto)]), tipo ∈ "titulo", "texto", "passo".
O texto muda conforme o sistema (Windows ou Mac) e os formatos vêm do
registro de conversões (nada escrito à mão que possa ficar desatualizado).
"""

from __future__ import annotations

import sys
from collections import defaultdict

from conversor import __version__

PAGINA = "https://github.com/Kiuwar/Lotus"


def _formatos() -> list[tuple[str, str]]:
    from conversor.core import registry

    por_categoria: dict[str, set] = defaultdict(set)
    total = 0
    for c in registry.all_converters():
        por_categoria[c.category].add(c.source)
        total += 1
    linhas = [("texto", f"O Lotus faz {total} conversões. De onde parte cada grupo:")]
    for cat in sorted(por_categoria):
        linhas.append(("passo", f"{cat}: " + ", ".join(sorted(f.upper() for f in por_categoria[cat]))))
    linhas.append(("texto", "Ao adicionar arquivos, o menu \"Converter para\" mostra só os formatos que "
                            "servem para todos eles. Algumas conversões precisam do Microsoft Word/"
                            "PowerPoint (Windows), do textutil (Mac) ou do ffmpeg (áudio e vídeo); sem "
                            "eles aparecem como indisponíveis, com o motivo."))
    return linhas


def secoes(sistema: str | None = None) -> list[tuple[str, list[tuple[str, str]]]]:
    sistema = sistema or sys.platform
    mac = sistema == "darwin"
    explorador = "Finder" if mac else "Explorer"
    atalho = "⌥ Option + ⇧ Shift + clique" if mac else "Ctrl + Shift + clique"

    comecar = [
        ("titulo", "Converter arquivos"),
        ("passo", "1. Clique em \"＋ Adicionar arquivos…\" (ou arraste os arquivos para o Lotus)."),
        ("passo", "2. Escolha o formato em \"Converter para\"."),
        ("passo", "3. Clique em \"Converter\". O arquivo novo fica na mesma pasta do original "
                  "(ou na pasta que você escolher)."),
        ("texto", "O arquivo original nunca é alterado, e o Lotus não sobrescreve nada sem você "
                  "marcar \"Sobrescrever arquivos existentes\". Se algo for perdido na conversão "
                  "(ex.: transparência, abas extras), o Lotus avisa no registro."),
    ]
    painel = [
        ("titulo", "Painel flutuante"),
        ("texto", f"No {explorador}, {atalho} sobre um arquivo abre um painel com os formatos. "
                  "Clique num formato para converter na hora."),
        ("passo", "Trocar o atalho ou ligar/desligar: Ferramentas → Atalho do painel flutuante…"),
        ("passo", "Mudar cores, tema (ex.: Holográfico) e tamanho: Ferramentas → Aparência…"),
    ]
    if mac:
        painel += [
            ("texto", "No Mac o painel precisa de duas permissões. A janela Ferramentas → Ativar o "
                      "painel no Mac… guia os 3 passos e marca ✓ sozinha."),
        ]
    menu = [("titulo", "Ação Rápida do Finder" if mac else "Menu do botão direito")]
    if mac:
        menu += [
            ("texto", "No Finder: clique direito num arquivo → Ações Rápidas → Converter com Lotus."),
            ("passo", "Instalar ou remover: Ferramentas → Instalar/Remover Ação Rápida do Finder."),
            ("passo", "Atalho de teclado para ela (sem permissões extras): Ajustes do Sistema → "
                      "Teclado → Atalhos de Teclado… → Serviços → Arquivos e Pastas → "
                      "\"Converter com Lotus\"."),
        ]
    else:
        menu += [
            ("texto", "No Explorer: clique direito num arquivo → \"Converter para\" → formato. "
                      "No Windows 11 ele fica em \"Mostrar mais opções\"."),
            ("passo", "Instalar ou remover: Ferramentas → Instalar/Remover menu do botão direito."),
        ]
    problemas = [
        ("titulo", "Quando algo dá errado"),
        ("passo", "Ferramentas → Diagnosticar e reparar: confere e corrige a instalação."),
        ("passo", "Ferramentas → Abrir pasta do log: o arquivo lotus.log tem os detalhes técnicos."),
        ("passo", "\"Indisponível: requer …\" ao lado de um arquivo: falta o programa indicado "
                  "(Word, PowerPoint, ffmpeg)."),
        ("passo", "PDF escaneado → TXT: o Lotus lê as páginas por OCR (reconhecimento de texto do "
                  "próprio sistema, sem internet). Confira o resultado: o OCR pode errar acentos e "
                  "números."),
    ]
    if mac:
        problemas += [
            ("passo", f"{atalho} não faz nada: Ferramentas → Diagnóstico do painel flutuante (Mac)…"),
            ("passo", "Depois de atualizar, a permissão de Acessibilidade \"não pega\": em Ajustes do "
                      "Sistema → Privacidade e Segurança → Acessibilidade, selecione Lotus, clique em "
                      "− e depois em + e escolha /Applications/Lotus.app."),
        ]
    else:
        problemas += [
            ("passo", "O ícone ao lado do relógio sumiu: ele pode estar dentro da setinha \"^\"; "
                      "arraste-o para fora."),
        ]
    privacidade = [
        ("titulo", "Privacidade (LGPD)"),
        ("texto", "As conversões acontecem só neste computador: nada é enviado à internet, não há "
                  "coleta de dados nem telemetria."),
        ("texto", "Única exceção, só quando você pede: Ferramentas → Procurar atualização consulta o "
                  "GitHub, que vê apenas o seu endereço IP. Uma vez por mês o Lotus só pergunta se "
                  "você quer procurar."),
        ("texto", "O log fica só no seu computador e contém nomes de arquivos; pode ser apagado."),
    ]
    sobre = [
        ("titulo", f"Lotus {__version__}"),
        ("texto", "Conversor de arquivos offline para Windows e Mac."),
        ("passo", "Atualizar: Ferramentas → Procurar atualização… (mantém suas configurações)."),
        ("texto", "Bibliotecas de terceiros: Pillow, pi-heif (libheif e libde265, LGPL-3.0), "
                  "openpyxl, fpdf2, Markdown, pypdf, pypdfium2, defusedxml"
                  + (", pyobjc, certifi." if mac else ", pywin32.")
                  + " Detalhes em docs/LICENCAS.md na página do projeto."),
        ("texto", f"Página do projeto: {PAGINA}"),
    ]
    return [("Começar", comecar), ("Formatos", [("titulo", "O que converte")] + _formatos()),
            ("Painel", painel), ("Ação Rápida" if mac else "Botão direito", menu),
            ("Problemas", problemas), ("Privacidade", privacidade), ("Sobre", sobre)]
