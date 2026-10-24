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
- A leitura da seleção pelo COM numa janela real do Explorer: o teste
  existe, mas no CI (run de 23/10/2026) foi **pulado** porque o runner do
  GitHub não abriu uma janela do Explorer. Continua sem verificação
  automática; só o teste manual confirma.

**Bug encontrado pelo CI Windows e corrigido:** se o `Lotus.exe` registrado
não existisse mais, o diagnóstico travava com `FileNotFoundError` ao tentar
iniciar o agente. No Linux o teste passava porque esse caminho só roda no
Windows. Agora o erro vai para o log e o diagnóstico informa "NÃO está
rodando".

## 4.3. PDF como origem e Word (versão 0.4.0)

**Problema relatado (fato):** na 0.3.0, ao adicionar um PDF, o campo
"Converter para" ficava vazio e o botão Converter mostrava "Adicione arquivos
válidos e escolha o formato". Causa: o registro não tinha nenhuma conversão
com PDF como origem (`targets_for("pdf") == []`), e a interface não explicava
isso. Não era defeito do motor; era escopo + mensagem ruim.

**Correção:**
- PDF → PNG/JPG com pypdfium2 (PDFium), uma imagem por página; o motor ganhou
  saídas múltiplas (`multi=True`): pasta temporária, validação de cada
  arquivo, nome final só no fim; pasta existente nunca é sobrescrita.
- PDF → TXT com pypdf; PDF escaneado falha com explicação (sem OCR).
- DOCX ↔ PDF via Microsoft Word (COM), disponível só com Word instalado, com
  limite de tempo que encerra apenas a instância aberta pelo Lotus.
- Mensagens: coluna Situação ("sem conversão para ZIP", "indisponível: requer
  o Microsoft Word") e motivo ao lado de "Converter para".

**Verificado:** conteúdo das imagens (tamanho em pixels da página A4 a
150 DPI, página não em branco), texto com acentos e separação por página,
PDF com senha, PDF só com senha de dono, falha no meio sem sobrar pasta,
executável PyInstaller convertendo PDF (Linux aqui; Windows no CI).

**NÃO verificado (sem Word no CI):** DOCX → PDF e PDF → DOCX com o Word de
verdade. A sequência de chamadas foi conferida com um Word simulado e as
constantes na documentação da Microsoft, mas só o teste no seu PC confirma.
Também não verificado: se o Word mostra algum aviso ao abrir PDF mesmo com
`DisplayAlerts = wdAlertsNone` (nesse caso, o limite de 3 minutos encerra a
instância e o Lotus explica).

## 4.4. Novo design estilo macOS e área de trabalho (versão 0.5.0)

**Decisões (com o usuário):** painel radial com os formatos separados por
grupo (arcos coloridos com rótulo); some ao clicar fora; moldura própria
na janela principal (Windows 10 não arredonda janelas); personalização de
cores, temas, tamanho, opacidade e forma; tema claro/escuro do sistema.

**Como os cantos ficam lisos no Windows 10 (fato):** o painel é uma janela
em camadas (`UpdateLayeredWindow`) com transparência por pixel, desenhada
com Pillow em 3× e reduzida. A janela principal usa `SetWindowRgn` (cantos
recortados; a borda do recorte é de 1 pixel, sem suavização — limitação do
Windows 10; no 11 o sistema suaviza).

**Verificado no CI Windows real:** a janela em camadas é criada; o canto
transparente deixa o clique passar para trás; mouse físico simulado
(SendInput) destaca a caixa e o clique converte; seleção da área de
trabalho via `FindWindowSW` funciona.

**Achado pelo CI e corrigido:** o painel em camadas não recebia `<Motion>`
quando o cursor era movido; agora consulta a posição do cursor a cada 30 ms.

**Verificado aqui (Linux):** geometria (sem sobreposição em todos os
formatos e tamanhos), contraste de todos os temas, pixels do desenho,
moldura (maximizar, arrastar, redimensionar, fechar), janela Aparência.
As imagens da galeria foram olhadas a cada mudança; dois defeitos visuais
achados assim foram corrigidos (rótulos cortados/fora do disco; texto
escuro no botão azul).

**NÃO verificado (teste manual seu):** o gesto real na área de trabalho e
no Explorer; a aparência no seu Windows 10 (fontes Segoe UI, escala de
tela); barra de tarefas/Alt+Tab com a moldura própria; minimizar e
restaurar pela barra de tarefas.

## 4.5. Versão para Mac (0.6.0)

**O que existe:** app de conversão (todas as conversões, menos as do Word),
Ação Rápida "Converter com Lotus" no clique direito do Finder, painel por
atalho (padrão ⌥ Option+⇧ Shift+clique, no Finder e na Mesa) e `.dmg` para
Apple Silicon e Intel.

**Fontes usadas para não inventar:** estrutura do workflow do Automator
copiada de workflows reais (repositório mb21/Pandoc-Mac-OS-X-Services;
artigo de andrewbaker.ninja de 2026-09-08 para a parte do Finder); nomes do
Quartz/AppKit são os da API C da Apple, conferidos um a um no CI do Mac;
pyobjc 12.2.2 (MIT, universal2) conferido no PyPI; executores macOS
(`macos-latest` = Apple Silicon, `macos-15-intel` = Intel) conferidos na
documentação do GitHub.

**Verificado no CI do Mac (quando ficar verde):** testes completos; nomes
do pyobjc existem; o workflow gerado é executado pelo `automator` e recebe
o arquivo; painel transparente criado; gancho sem permissão explica o que
fazer; `.app` empacotado converte (inclusive PDF); Ação Rápida instalada
pelo app aponta para o Lotus.app; `.dmg` monta e contém o app.

**NÃO verificado (teste manual seu):** permissões reais de Acessibilidade e
Automação; o gesto no Finder/Mesa; a Ação Rápida aparecendo no menu do
Finder; Gatekeeper ("Abrir Mesmo Assim"); aparência do painel transparente
(o CI tenta um print, mas o macOS pode bloquear a captura de tela).

## 4.6. Versão 0.7.0: mais formatos, ícone ao lado do relógio e flor de lótus

**Decisões e por quê:**
- **DOCX/PPTX → texto sem Office** com `zipfile` + `defusedxml`, sem
  `python-docx`/`python-pptx`: as duas puxariam `lxml` (biblioteca compilada,
  pacote maior em cada sistema). O formato (ECMA-376) é XML dentro de ZIP;
  `defusedxml` já vinha com o `fpdf2` e protege contra XML malicioso.
- **Estilos de título pelo NOME, não pelo ID:** o Word em português grava o
  ID localizado (`Ttulo1`), mas o nome interno é sempre `heading 1`
  (`word/styles.xml`). Ler só o ID quebraria todo documento em português.
- **Constantes do Office** conferidas na documentação da Microsoft e listadas
  no topo de `office.py`; o vigia de tempo do Word virou genérico e vale para
  o PowerPoint.
- **Ícone ao lado do relógio** com a API do pywin32 conferida no exemplo
  oficial do projeto; a thread só enfileira comandos (regra 11). O CI do
  Windows provou: ícone entra, menu e duplo clique chegam, ícone sai.
- **Ícone da flor** desenhado por código (sem imagem de terceiros, sem
  licença a checar); tamanhos ≤ 32 px têm desenho próprio (mais legível).

**Erros que os testes pegaram nesta versão (e a lição):**
- Painel radial: a distância mínima entre caixas só valia na horizontal; na
  diagonal duas caixas se sobrepunham. Só apareceu com 12 caixas (vídeo).
  Lição: geometria se testa com o pior caso real, não com o caso típico.
- "Mais…" enchia os grupos em ordem e o grupo Vídeo sumia inteiro.
- MPEG-2 só aceita taxas de quadros padrão; este ffmpeg aceitou 10 q/s, mas
  outras versões recusam — a taxa é ajustada pela regra do formato, não pelo
  comportamento de uma versão.
- Codificador interno do Opus/Vorbis só funciona em modo experimental e com
  limites (48 kHz / 2 canais): descoberto rodando o ffmpeg, não lendo.
- `--listar` dizia "requer ffmpeg" para conversões do Word.

**NÃO verificado (teste manual seu):** conversões reais com Word e
PowerPoint instalados (o CI não tem Office); aparência do ícone ao lado do
relógio no seu Windows 10; abrir *Configurar atalho…* e *Aparência…* pelo
ícone.

## 5. Limitações conhecidas (não implementadas de propósito)

- **DOCX/XLSX/PPTX → PDF com layout fiel:** exige Microsoft Word/Office
  (automação COM) ou LibreOffice instalado. Pode ser adicionado como
  conversão "disponível se o Office/LibreOffice estiver instalado", no mesmo
  modelo do ffmpeg.
- **PDF → Word sem o Microsoft Word:** não há conversão offline confiável.
  Com Word, o resultado é aproximado (ver 4.3).
- **OCR (PDF escaneado → texto):** não incluído (exigiria Tesseract).
- **Vários arquivos no botão direito:** o Explorer abre um processo por
  arquivo, então cada um mostra seu aviso. Juntar tudo numa janela só
  exigiria um mecanismo de instância única (ou extensão COM do Explorer).
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
