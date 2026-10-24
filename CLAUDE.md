# Regras para o Claude neste repositório

Este arquivo é lido automaticamente pelo Claude Code em toda sessão. Ele é a
"memória persistente" do projeto: as regras abaixo valem sempre.

## O projeto

Lotus: aplicativo Windows e macOS (Python + tkinter, empacotado com
PyInstaller) que converte arquivos **localmente**, sem internet.

- `conversor/core/registry.py` — fonte única de verdade das conversões.
- `conversor/core/engine.py` — detecta, converte, valida, grava (atômico).
- `conversor/core/detect.py` — formato real pelo conteúdo, não pela extensão.
- `conversor/core/validate.py` — reabre a saída antes de aceitar.
- `conversor/converters/` — uma família de formatos por módulo
  (`pdf.py`: PDF→PNG/JPG/TXT; `office.py`: Word e PowerPoint via COM;
  `office_texto.py`: DOCX→TXT/MD/HTML e PPTX→TXT/MD sem Office;
  `media.py`: áudio e vídeo via ffmpeg).
  Conversor com `multi=True` recebe uma pasta e grava várias saídas.
- `conversor/launcher.py` — entrada do Lotus.exe (janela, menu, reparo).
- `conversor/shell.py` — menu do botão direito (registro, HKCU).
- `conversor/menu.py` — janelas abertas pelo botão direito.
- `conversor/diagnostics.py` — diagnóstico e reparo da instalação.
- `conversor/atalho/` — painel flutuante (Ctrl+Shift+clique): `config.py`
  (atalho e validação), `gesto.py` (lógica pura do gesto), `winapi.py`
  (ctypes), `selecao.py` (seleção do Explorer via COM), `agente.py`
  (processo em segundo plano), `painel.py`, `janela_config.py`, `controle.py`,
  `bandeja.py` (ícone ao lado do relógio; só enfileira comandos).
- `conversor/ui/` — visual estilo macOS: `tema.py` (temas, cores, contraste),
  `grupos.py`, `radial.py` (geometria pura do painel), `render.py` (desenho
  Pillow 3× + cache), `camadas.py` (janela em camadas do Windows),
  `widgets.py` (pílula, cartão, estilo ttk), `moldura.py` (moldura própria),
  `janela_aparencia.py`.
- `scripts/gerar_previas.py` — imagens do design (artefato "Galeria-de-design" no CI).
- `conversor/ui/icone.py` — ícone da flor de lótus desenhado por código;
  `scripts/gerar_icone.py` grava `conversor/recursos/lotus.{ico,icns,png}`
  (o teste falha se estiverem desatualizados).
- `conversor/atalho/mac.py` — agente do Mac (Quartz Event Tap, seleção do
  Finder via osascript, trava de instância, LaunchAgent).
- `conversor/acao_rapida.py` — Ação Rápida do Finder (clique direito no Mac).
- `scripts/ajustar_app_mac.py`, `scripts/capturar_mac.py` — empacotamento/diagnóstico Mac.
- `installer/lotus.iss` — instalador Inno Setup (gerado e testado no CI).
- `docs/FORMATOS.md` — GERADO por `scripts/gerar_formatos.py`. Não editar à mão.
- `docs/ANALISE.md` — por que o projeto é assim e como evitar erros de IA.

## Comandos

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q                 # no Linux: xvfb-run -a python -m pytest -q
python scripts/gerar_formatos.py    # após mudar o registro
python -m conversor --listar
```

## Regras obrigatórias (anti-erro / anti-alucinação)

1. **Não declare que algo funciona sem mostrar a saída do teste.** "Deve
   funcionar" não é aceito. Rode `pytest` e cite o resultado.
2. **Toda conversão nova precisa de:** registro em `@register`, gerador de
   amostra em `tests/conftest.py`, validador em `validate.py` (se for formato
   de saída novo) e ao menos um teste de CONTEÚDO em `test_behaviour.py`
   (verificar que o dado saiu certo, não só que o arquivo existe).
3. **Não invente API de biblioteca.** Antes de usar uma função/parâmetro que
   não aparece no código existente, confirme na documentação oficial ou
   rodando `python -c "help(...)"` na versão fixada em `requirements.txt`.
4. **Não invente versões.** Confirme com `pip index versions <pacote>` antes
   de alterar `requirements.txt`. Atualize uma dependência por vez.
5. **Não prometa conversões impossíveis offline.** Ex.: DOCX→PDF fiel exige
   Word ou LibreOffice; PDF→DOCX fiel não existe de forma confiável. Se for
   pedido, explique a limitação antes de codar.
6. **Nunca altere o arquivo de origem e nunca sobrescreva sem permissão.**
   Toda escrita passa por `engine.convert_file`.
7. **Não altere dados silenciosamente.** Perda (transparência, quadros de GIF,
   planilhas extras, encoding) gera aviso em `options["_warnings"]`.
8. **Sem rede.** O app não faz requisições, não tem telemetria. Qualquer
   mudança nisso exige revisão de privacidade (LGPD) e aviso ao usuário.
   Única exceção aprovada (0.8): `conversor/atualizar.py`, só quando a pessoa
   pede (menu ou "Sim" no lembrete mensal, que não acessa a rede), só para
   hosts do GitHub em HTTPS, sem enviar dado algum, e com SHA-256 conferido.
9. **Separe fato de suposição** ao responder: o que foi testado aqui (Linux),
   o que só o CI no Windows confirma, e o que é opinião.
10. Mensagens ao usuário em português do Brasil.
11. **Threads nunca recebem objetos do tkinter** (nem `self` de uma janela):
    só dados e filas. Senão o coletor de lixo pode destruir o objeto fora da
    thread principal e derrubar o processo ("Tcl_AsyncDelete").
12. **Registro do Windows só em HKCU, só sob a chave `Lotus.Converter` e o
    valor `Lotus.Atalho` em `...\CurrentVersion\Run`.**
    Nunca apagar chaves de outros programas. Testes no Linux usam
    `tests/fake_winreg.py`; o comportamento real é validado no CI Windows.
13. Erro novo que o usuário pode resolver → mensagem em `core/errors.py`
    com "Como resolver". Reparo automático só quando não altera dados
    (ex.: salvar com outro nome), sempre com aviso.
14. **Gancho de mouse:** o callback só decide e enfileira (nada de COM,
    disco ou janela lá dentro). Eventos injetados sempre passam. Nunca usar
    gancho de teclado (WH_KEYBOARD_LL): para tecla, só RegisterHotKey.
15. **ctypes:** toda função da API declara `argtypes`/`restype`; toda
    estrutura nova ganha teste de `sizeof` em `test_atalho_windows.py`.
16. O que só um humano consegue testar (gesto real no Explorer) deve ser
    dito como pendente, nunca como verificado.
17. **Word e PowerPoint (office.py):** constantes conferidas em
    learn.microsoft.com e listadas no topo do arquivo (WdSaveFormat,
    PpSaveAsFileType, MsoTriState). Sem Office no CI: a lógica é testada com
    Word/PowerPoint simulados e o uso real é teste manual — nunca dizer que
    foi verificado. XML do Office lido só com `defusedxml` (arquivo do usuário).
18. **Design:** toda mudança visual passa pela galeria
    (`scripts/gerar_previas.py`) e é OLHADA antes do commit. Texto precisa de
    contraste ≥ 4,5:1 (`tema.legivel`); exceção: texto branco em botão
    colorido a partir de 3:1 (padrão macOS, `tema.texto_sobre`).
19. **Janela em camadas:** pixel com alfa > 0 captura cliques; sombras
    passam pelo corte de alfa < 8 em `render.desenhar_base`.
20. **Mac:** nomes do pyobjc só se estiverem em `mac.NOMES_QUARTZ` (o CI do
    Mac confere que existem). Nunca recarregar módulos (`importlib.reload`)
    nos testes; para simular outro sistema, use um subprocesso.
21. A Ação Rápida segue a estrutura de workflows reais (fontes no topo de
    `acao_rapida.py`) e é EXECUTADA no CI com `automator -i`.
22. **`after` do Tk:** em janela que fecha (painel, aviso), todo `after`
    pendente é cancelado ao fechar e no `<Destroy>`. Senão o Tcl chama um
    comando apagado e o Tk abre o diálogo de erro — no Mac é modal e trava
    o programa. Os testes falham em qualquer erro Tcl em segundo plano
    (`tests/conftest.py`); o app manda esses erros ao log (`registrar_erros_tcl`).
