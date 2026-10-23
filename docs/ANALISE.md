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

**Verificado nesta sessão (Linux, Python 3.12):**
- 156 testes passando, incluindo as 122 conversões e a GUI (xvfb).
- Executável de linha de comando gerado com PyInstaller 6.22.3 e testado
  (listou as 122 conversões, converteu PNG→PDF e CSV→XLSX, recusou CSV→PDF
  com mensagem correta).

**Pendente — só o CI no Windows confirma:**
- Testes rodando em `windows-latest` (fonte Arial no PDF, caminhos, tkinter).
- Build do `KiuwarConversor.exe` com janela e o teste do executável.
- Conversões de mídia no Windows dependem do `choco install ffmpeg` no CI;
  se ele falhar, esses testes aparecem como *skipped* — confira o log.

Até o CI ficar verde no Windows, **não é correto afirmar que o app funciona
no Windows**; só que o código está pronto e testado em Linux.

---

## 5. Limitações conhecidas (não implementadas de propósito)

- **DOCX/XLSX/PPTX → PDF com layout fiel:** exige Microsoft Word/Office
  (automação COM) ou LibreOffice instalado. Pode ser adicionado como
  conversão "disponível se o Office/LibreOffice estiver instalado", no mesmo
  modelo do ffmpeg.
- **PDF → Word editável:** não há conversão offline confiável; resultados
  variam muito conforme o PDF. Não recomendado prometer.
- **PDF → imagem:** exige um renderizador (ex.: PyMuPDF, licença AGPL — que
  obrigaria abrir o código do app se distribuído; avaliar antes).
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
e `build-windows` verdes e baixar o artefato **KiuwarConversor-windows**
para testar manualmente num PC com Windows.
