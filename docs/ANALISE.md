# Análise: como o Claude pode construir este conversor sem erros nem alucinação

## Resposta curta

O Claude consegue construir um conversor de arquivos para Windows com
confiabilidade **desde que nada dependa da palavra dele**. A estratégia
deste projeto é transformar cada afirmação ("converte X em Y", "a versão Z
existe", "funciona no Windows") em algo **verificado por máquina**: teste,
validador de saída, CI no Windows real ou consulta ao PyPI. Onde não há
verificação, a regra é declarar a limitação em vez de supor.

Este documento separa três coisas: **fato verificado** (rodado nesta
sessão), **pendente de verificação** (só o CI no Windows confirma) e
**opinião/recomendação**.

---

## 1. Onde uma IA costuma errar neste tipo de projeto

| Risco | Exemplo concreto | Como foi bloqueado aqui |
|---|---|---|
| Inventar função ou parâmetro de biblioteca | Usar um argumento que não existe no Pillow/fpdf2 | Todo caminho é executado por teste; API errada quebra o teste |
| Inventar ou "chutar" versão de pacote | `pillow==99.0` | Versões conferidas com `pip index versions` e fixadas em `requirements.txt` |
| Prometer conversão que não implementou | README dizendo "converte DOCX" | `docs/FORMATOS.md` é **gerado do código**; teste falha se divergir |
| Prometer conversão impossível offline | DOCX→PDF fiel, PDF→Word editável | Não incluídas; documentadas como limitação (seção 5) |
| Dizer "funciona" sem rodar | "O código deve estar correto" | `CLAUDE.md` exige saída de teste; CI roda em cada push |
| Testar só que o arquivo existe | PDF vazio "passa" | Validador reabre a saída + testes de **conteúdo** |
| Ignorar particularidades do Windows | Encoding cp1252, janela de console piscando com ffmpeg, DPI | Tratados no código e testados no runner `windows-latest` |
| Alterar dados sem avisar | CEP `01234` virar `1234`; `=SOMA()` virar fórmula | Valores de CSV mantidos como texto; `=` forçado como texto; testes cobrem |
| Perder o arquivo do usuário | Sobrescrever origem ou deixar saída corrompida | Escrita em temporário → validação → `os.replace`; nunca sobrescreve sem opção |

### Evidência: bugs reais que os testes pegaram nesta sessão (fato verificado)

1. **Separador de CSV errado.** A primeira versão usava `csv.Sniffer` da
   biblioteca padrão. Com um CSV brasileiro típico (`nome;preço` /
   `João;10,50`) ele escolheu `,` como separador, gerando uma planilha com
   tudo numa coluna. O teste de matriz **passou** (o arquivo existia); só o
   teste de conteúdo pegou. Substituído por detecção por consistência de
   colunas (`guess_delimiter`), com testes próprios.
2. **Arquivos duplicados na interface.** Selecionar o mesmo arquivo duas
   vezes na mesma operação o adicionava duas vezes. Pego pelo teste da GUI.

Lição: "todos os testes passaram de primeira" deve gerar **desconfiança**,
não confiança. Os 122 testes de matriz passaram logo na primeira execução;
foram os testes de conteúdo escritos depois que revelaram o erro 1.

---

## 2. Arquitetura escolhida e por quê

```
conversor/
  core/registry.py   fonte única de verdade (o que converte)
  core/detect.py     formato real pelo conteúdo (magic bytes)
  core/engine.py     orquestra: detecta → converte → valida → grava
  core/validate.py   reabre a saída com leitor independente
  converters/        images.py, data.py, documents.py, media.py
  cli.py, gui.py     duas interfaces finas sobre o mesmo motor
tests/               matriz completa + conteúdo + CLI + GUI + docs
scripts/gerar_formatos.py → docs/FORMATOS.md
```

Princípios:

- **Registro único.** Interface, CLI, documentação e testes leem a mesma
  lista. É impossível o menu oferecer algo que não foi testado.
- **Interface fina.** Toda lógica fica no motor, testável sem tela. A GUI
  só monta botões e repassa chamadas (e mesmo assim é testada com display
  virtual).
- **Falhar alto.** Erro de biblioteca vira mensagem clara; conversão que não
  existe lista as alternativas; nunca há saída parcial.

### Alternativas consideradas (opinião fundamentada)

| Opção | A favor | Contra | Decisão |
|---|---|---|---|
| **Python + tkinter** (escolhida) | Testável de ponta a ponta neste ambiente; tkinter vem com o Python do Windows; bibliotecas maduras | Visual mais simples; executável maior que um nativo (o CLI empacotado no Linux deu ~24 MB, medido) | ✔ menor risco de código não verificado |
| C# / .NET (WPF ou WinUI) | Nativo, visual moderno, executável menor | Não há como compilar/testar neste ambiente Linux → código sairia **sem verificação**, exatamente o risco a evitar | ✘ por ora; viável depois com CI Windows |
| Python + PySide6 (Qt) | Interface mais bonita, arrastar-e-soltar nativo | Dependência grande; licença LGPL exige cuidado na distribuição | Possível evolução |
| Electron / Tauri | UI web | Pesado (Electron) ou exige Rust (Tauri); conversões continuariam dependendo de bibliotecas nativas | ✘ |

Contra-argumento honesto à escolha: se a prioridade for aparência e
tamanho do instalador, C# seria melhor. A escolha aqui privilegiou
**verificabilidade**, que é o que o pedido exigiu.

---

## 3. Mecanismos anti-alucinação, um a um

1. **Teste de matriz** (`tests/test_matrix.py`): para *cada* par registrado,
   gera um arquivo real de origem (via Pillow/openpyxl/ffmpeg), converte e
   valida. Registrar uma conversão sem amostra faz o teste falhar.
2. **Validador de saída** (`validate.py`): imagens são reabertas com
   `Image.verify()` e a assinatura binária é conferida; PDF precisa de
   `%PDF-` e `%%EOF`; JSON/XLSX/CSV são reabertos; mídia passa pelo
   `ffprobe` quando disponível. Formato sem validador = erro.
3. **Testes de conteúdo** (`tests/test_behaviour.py`): acentos no PDF
   (extraídos com pypdf), tipos no JSON, zeros à esquerda, transparência
   virando branco, rotação EXIF, tamanhos do ICO, duração do áudio.
4. **Documentação gerada** + teste de sincronia (`tests/test_docs.py`).
5. **Versões verificadas e fixadas.** Licenças conferidas no metadado dos
   pacotes instalados: Pillow (MIT-CMU), openpyxl (MIT), fpdf2
   (LGPL-3.0-only), Markdown (BSD-3-Clause).
6. **CI em Windows real** (`.github/workflows/ci.yml`): roda os testes em
   `windows-latest` e, depois de empacotar, **executa o `.exe`** e confere
   que o PDF foi gerado. Testar o código-fonte não basta: o empacotamento
   pode esquecer módulos.
7. **`CLAUDE.md`**: memória persistente do projeto. Toda sessão futura do
   Claude Code lê as regras (não declarar sucesso sem teste, não inventar
   API/versão, não prometer conversão impossível).

---

## 4. Status de verificação

**Verificado em Linux (Python 3.12):** 180 testes passando (versão 0.2.0),
incluindo as 122 conversões, a interface e as janelas do menu (xvfb).

**Verificado no CI Windows (`windows-latest`), versão 0.1.0:** 156 testes
passando sem nenhum pulado (inclusive áudio/vídeo com ffmpeg), build do
`.exe` e teste do executável empacotado. A versão 0.2.0 só conta como
verificada no Windows depois que o CI dela ficar verde.

## 4.1. Menu do botão direito e reparação de erros (versão 0.2.0)

**Como funciona (fato):** chaves em
`HKCU\Software\Classes\SystemFileAssociations\.<ext>\shell\Lotus.Converter`,
com `SubCommands` vazio e os itens na subchave `shell`. Por usuário, sem
administrador. As chaves são geradas do registro de conversões, então o
menu não pode oferecer formato que não existe (há teste para isso).

**O que é verificado automaticamente:**
- Linux: montagem das chaves, instalação/remoção/reparo com um registro
  simulado (`tests/fake_winreg.py`), janelas do menu com display virtual.
- CI Windows: instalação e remoção no **registro real**, e o executável
  empacotado instalando o menu e apontando para o `Lotus.exe`.

**O que NÃO dá para verificar automaticamente (precisa de teste manual):**
- O Explorer **exibir** o submenu ao clicar com o botão direito: o CI não
  tem como clicar no Explorer. Confirmar num PC real, no Windows 10 e no 11
  ("Mostrar mais opções").
- A aparência do aviso e da janela "Escolher formato…" no Windows.

**Falha intermitente encontrada e tratada:** durante os testes, o processo
abortou uma vez. O sintoma é compatível com um problema conhecido do
tkinter: objeto do Tk coletado pelo coletor de lixo dentro da thread de
conversão. A causa provável foi removida (threads recebem só dados) e a
suíte rodou 8 vezes seguidas sem falha. Como a falha original não se
reproduziu de novo, isso reduz o risco mas **não prova** que ele acabou.

**Reparação de erros:** ver README, seção "Quando algo dá errado". Regra
adotada: reparo automático só quando não altera o conteúdo (salvar com
outro nome, ler a parte íntegra de uma imagem, regravar o menu) e sempre
com aviso; dado ambíguo não é "consertado" por adivinhação.

## 4.2. Painel flutuante (Ctrl+Shift+clique) e instalador (versão 0.3.0)

**Por que Ctrl+Shift e não Ctrl (fato):** no Explorer, Ctrl+clique
marca/desmarca arquivos numa seleção múltipla. Usar esse gesto tiraria essa
função do Windows. O padrão é Ctrl+Shift+clique e o usuário pode trocar.

**Como funciona:** um processo em segundo plano (`Lotus.exe --agente`)
instala um gancho de mouse de baixo nível (`WH_MOUSE_LL`). Quando o gesto
acontece numa janela do Explorer, o clique é engolido; o Lotus solta as
teclas virtualmente e simula um clique simples para o Explorer selecionar
só aquele arquivo, lê a seleção pelo COM `Shell.Application` e abre o painel.
Com várias abas (Windows 11), usa a aba cuja seleção mudou.

**Verificado automaticamente:**
- Linux: validação dos atalhos, máquina de estados do gesto (inclusive
  ignorar cliques injetados e janelas que não são do Explorer), escolha da
  aba, configuração corrompida, início automático (registro simulado),
  janela de configuração e painel (display virtual).
- CI Windows: tamanhos das estruturas da API; gancho instala/desinstala;
  tecla de atalho registra; instância única e parada do agente; leitura da
  seleção de uma janela real do Explorer (se o runner abrir o Explorer —
  senão o teste aparece como *skipped* no log); instalador gerado,
  instalação silenciosa, menu e início automático apontando para a pasta
  instalada, agente rodando, conversão pelo programa instalado e
  desinstalação removendo tudo.

**NÃO verificado (só dá para testar à mão num PC):**
- O gesto real: segurar Ctrl+Shift, clicar num arquivo do Explorer e o
  painel aparecer. O CI não consegue posicionar o mouse sobre um arquivo
  específico do Explorer de forma confiável.
- Se soltar Alt/Win virtualmente evita mesmo o menu Iniciar/menu da janela
  (técnica da tecla-máscara 0xE8, usada pelo AutoHotkey) em todas as
  versões do Windows.
- Comportamento com antivírus de terceiros (podem bloquear ganchos).

## 5. Limitações conhecidas (não implementadas de propósito)

- **DOCX/XLSX/PPTX → PDF com layout fiel:** exige Microsoft Word/Office
  (automação COM) ou LibreOffice instalado. Pode ser adicionado como
  conversão "disponível se o Office/LibreOffice estiver instalado", no mesmo
  modelo do ffmpeg.
- **PDF → Word editável:** não há conversão offline confiável; resultados
  variam muito conforme o PDF. Não recomendado prometer.
- **PDF → imagem:** exige um renderizador (ex.: PyMuPDF, licença AGPL — que
  obrigaria abrir o código do app se distribuído; avaliar antes).
- **Vários arquivos no botão direito:** o Explorer abre um processo por
  arquivo, então cada um mostra seu aviso. Juntar tudo numa janela só
  exigiria um mecanismo de instância única (ou extensão COM do Explorer).
- **Painel flutuante na área de trabalho:** não suportado (só janelas de
  pastas do Explorer). A área de trabalho exige outra interface COM.
- **Arrastar e soltar** na janela: tkinter puro não suporta; dá para abrir
  arquivos arrastando-os sobre o ícone do `.exe` (já tratado em `gui.main`).
- **Assinatura de código:** o `.exe` não é assinado; o Windows SmartScreen
  e alguns antivírus podem alertar (comum com PyInstaller). Resolver exige
  certificado de assinatura de código (custo anual).
- **Instalador** (MSI/Inno Setup) e atualização automática: não feitos.

---

## 6. LGPD

Como o processamento é local, sem rede e sem telemetria, o aplicativo não
coleta nem trata dados pessoais por conta própria; o usuário processa os
próprios arquivos no próprio computador. Isso reduz drasticamente as
obrigações da Lei 13.709/2018 para o desenvolvedor. **Isso muda** se forem
adicionados: telemetria, relatório de erros enviado pela internet, conta de
usuário, licenciamento online ou conversão na nuvem. Nesses casos será
preciso base legal, política de privacidade e informação clara ao usuário.
(Avaliação geral, não parecer jurídico.)

---

## 7. Como pedir novas funções ao Claude (fluxo recomendado)

1. Peça **primeiro um plano curto** e as limitações do formato pedido.
2. Exija: "registre a conversão, crie amostra real, teste de conteúdo e
   rode `pytest`; mostre a saída".
3. Para bibliotecas novas: "confirme versão com `pip index versions` e a
   licença no metadado antes de adicionar".
4. Depois do push, confira o CI no GitHub (aba *Actions*) — o resultado no
   Windows é o que vale.
5. Desconfie de respostas como "deve funcionar", "provavelmente" ou de
   recursos que não aparecem em `docs/FORMATOS.md`.

## Próximo passo recomendado

Abrir a aba *Actions* do repositório, confirmar o job `test (windows-latest)`
e `build-windows` verdes e baixar o artefato **Lotus-windows**
para testar manualmente num PC com Windows.
