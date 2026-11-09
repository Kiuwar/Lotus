# Lotus

Conversor de arquivos para **Windows e Mac** que funciona **no seu
computador**, sem internet: imagens, PDF (inclusive escaneado), Word,
PowerPoint, planilhas, áudio, vídeo e **arquivos para impressão 3D** — 449
conversões. Os arquivos nunca saem do computador.

## Baixar

| Sistema | Arquivo |
|---|---|
| **Windows 10/11** | [**LotusSetup.exe**](https://github.com/Kiuwar/Lotus/releases/latest/download/LotusSetup.exe) |
| **Mac com chip Apple** (M1, M2, M3, M4…) | [**Lotus-Mac-AppleSilicon.dmg**](https://github.com/Kiuwar/Lotus/releases/latest/download/Lotus-Mac-AppleSilicon.dmg) |
| **Mac com processador Intel** | [**Lotus-Mac-Intel.dmg**](https://github.com/Kiuwar/Lotus/releases/latest/download/Lotus-Mac-Intel.dmg) |

Os links baixam sempre a versão mais nova, sem conta no GitHub. Todas as
versões, com o código SHA-256 de cada arquivo:
[Releases](https://github.com/Kiuwar/Lotus/releases). Quem já tem o Lotus
atualiza pelo próprio app (*Ferramentas → Procurar atualização…*).

## O que converte

| Área | Conversões |
|---|---|
| **Imagens** | PNG, JPG, WEBP, BMP, GIF, TIFF, ICO e AVIF entre si e para PDF; **fotos do iPhone (HEIC/HEIF)** para todas elas (o Lotus lê HEIC, não grava) |
| **PDF** | Para PNG/JPG (uma imagem por página) e para TXT — **inclusive PDF escaneado**, lido por OCR do próprio Windows/Mac, sem internet. **Separar** (um PDF por intervalo, ou só as páginas escolhidas) e **juntar** vários PDFs e imagens num PDF, na ordem que você escolher |
| **Word** | Sem Word: DOCX → TXT/Markdown/HTML; TXT/Markdown/HTML → DOCX (com estilos de título); DOCX → PDF simples. Com o Word (Windows): DOCX, DOC, RTF e ODT entre si, PDF idêntico ao Word, XPS e PDF → DOCX. No Mac: DOCX, DOC, RTF e ODT pelo `textutil` do macOS |
| **PowerPoint** | Sem PowerPoint: PPTX → TXT/Markdown (texto e notas). Com o PowerPoint (Windows): PPTX, PPT e ODP entre si, PDF e uma imagem por slide |
| **Planilhas e dados** | CSV, JSON e XLSX entre si; XLSX/CSV/JSON → HTML, Markdown e PDF para ler e imprimir (todas as abas, vírgula decimal, datas dd/mm/aaaa) |
| **Texto** | TXT → PDF; Markdown e HTML → PDF, DOCX e TXT; HTML → Markdown |
| **Áudio** (com ffmpeg) | MP3, WAV, OGG, FLAC, M4A, AAC, OPUS, WMA, AIFF; áudio de qualquer vídeo; áudio → MP4 (tela preta) |
| **Vídeo** (com ffmpeg) | MP4, MKV, WEBM, AVI, MOV, WMV, MPEG, M4V; vídeo → GIF animado e → imagem |
| **Impressão 3D** (em mm) | STL, OBJ, 3MF, PLY, OFF e GLB entre si; modelo → imagem PNG/JPG; **SVG → STL/3MF** (áreas preenchidas viram peça com espessura); **foto → litofania** STL/3MF; **SVG ↔ DXF** (corte a laser); SVG → PNG/JPG/WEBP/PDF |

Lista completa, gerada a partir do código: [docs/FORMATOS.md](docs/FORMATOS.md).
Tudo o que não depende do Word/PowerPoint é executado de verdade nos testes
automáticos (Windows, Mac e Linux); Word e PowerPoint são testados com o
programa simulado, porque o servidor de testes não tem Office.

## Três jeitos de converter

**1. Janela do Lotus.** Clique em *＋ Adicionar arquivos…* (ou arraste os
arquivos sobre o ícone do Lotus), escolha em *Converter para* e clique em
*Converter*. O menu só mostra formatos que servem para **todos** os arquivos
adicionados; quando um arquivo não tem conversão, a coluna *Situação* diz o
motivo.

**Separar e juntar PDFs.** Na janela, *Separar PDF…* (ex.: `1-3, 4-9, 10-`
gera um PDF por intervalo; ou "só estas páginas", ex.: `2, 5-7`) e *Juntar em
um PDF* (PDFs e imagens da lista, com ↑↓ para a ordem). Também no botão
direito: num PDF, *Separar PDF…*; com vários PDFs/imagens selecionados,
*Juntar em um PDF…*. No Mac, pela Ação Rápida. Os originais não são alterados.

**2. Clique direito no arquivo.**
- **Windows:** *Converter para* → formato (ou *Escolher formato…*). No
  Windows 11 fica em *Mostrar mais opções*. Instalar/remover: *Ferramentas*.
- **Mac:** *Ações Rápidas → Converter com Lotus* (instalada na 1ª abertura).
  Dá para criar um atalho de teclado para ela em *Ajustes do Sistema →
  Teclado → Atalhos de Teclado… → Serviços → Arquivos e Pastas*.

**3. Painel flutuante (atalho).** No Explorer ou na área de trabalho,
**Ctrl+Shift+clique** num arquivo (no Mac, no Finder ou na Mesa,
**⌥ Option+⇧ Shift+clique**). Aparece o painel **Vidro**: o arquivo no
centro e cada formato como uma **pílula de vidro** em volta, como os botões
do iPhone. Passe o mouse e clique para converter: a pílula mostra "…" e
depois ✓ (ou ✕ com a explicação). O painel some depois do ✓, com *Esc*,
clicando fora ou após 15 s. Com mais de 18 formatos, *Mais…* abre a lista
completa.
- No Windows o vidro desfoca o que está atrás do painel de verdade; no Mac
  ele é translúcido (desfocar o fundo lá exigiria a permissão de Gravação de
  Tela). O texto é ajustado para ficar legível sobre qualquer fundo.
- Atalho configurável em *Ferramentas → Atalho do painel flutuante…*:
  Ctrl/Shift/Alt/Win com qualquer botão do mouse ou com uma tecla (tecla só
  no Windows). Atalhos que atrapalhariam o uso normal são recusados.

**Aparência (*Ferramentas → Aparência…*):** estilo do painel (**Vidro**,
Radial ou Cartão), cor do vidro (Azul, Neutro, Rosa, Verde, Roxo, Grafite ou
qualquer cor), intensidade (de limpo a fosco), animação de entrada, tamanho e
claro/escuro — com prévia grande ao vivo. Radial e Cartão têm temas prontos e
cores por grupo de formato.

**Ícone sempre à mão:** no Windows, a flor fica **ao lado do relógio**
(duplo clique abre o Lotus; clique direito: converter, painel, atalho,
aparência). No Mac, fica na **barra de menus**, com *Converter os arquivos
selecionados no Finder…* — que funciona sem a permissão de Acessibilidade.

**Linha de comando:**

```
conversor-cli.exe foto.png planilha.csv --para pdf
conversor-cli.exe logo.svg --para stl --espessura 3 --largura 50
conversor-cli.exe foto.jpg --para stl --modo litofania
conversor-cli.exe contrato.pdf --separar "1-3, 4-"
conversor-cli.exe contrato.pdf --extrair "2, 5-7"
conversor-cli.exe capa.jpg contrato.pdf anexo.pdf --juntar final.pdf
conversor-cli.exe --listar
```

## Instalar no Windows

1. Baixe o [**LotusSetup.exe**](https://github.com/Kiuwar/Lotus/releases/latest/download/LotusSetup.exe)
   e execute. Não precisa de administrador (instala em
   `%LOCALAPPDATA%\Programs\Lotus`).
2. O instalador não tem assinatura digital paga: se o SmartScreen avisar,
   clique em *Mais informações → Executar assim mesmo*.
3. Escolha: menu do botão direito, painel flutuante, ícone ao lado do relógio
   e atalho na área de trabalho.

Para remover: *Configurações → Aplicativos → Lotus → Desinstalar* (remove
menu, painel e início automático; sua configuração em `%APPDATA%\Lotus` e os
arquivos convertidos ficam).

## Instalar no Mac

1. Baixe o `.dmg` do seu Mac (Menu  → Sobre Este Mac → "Chip" ou
   "Processador"), abra e arraste o **Lotus** para **Aplicativos**.
2. Na 1ª abertura: *Ajustes do Sistema → Privacidade e Segurança → Abrir
   Mesmo Assim* (o Lotus não tem assinatura paga da Apple).
3. A janela **Ativar o Lotus no Mac** guia os passos e marca ✓ sozinha:
   ligar o painel; permitir **Acessibilidade** (para o ⌥⇧+clique); permitir
   que o Lotus leia a seleção do **Finder**; Ação Rápida; atalho de teclado
   (opcional). Para reabrir: *Ferramentas → Ativar o painel no Mac…*.

**⌥⇧+clique não faz nada?** *Ferramentas → Diagnóstico do painel flutuante
(Mac)…* mostra, item por item, o que falta e como resolver. Casos comuns:
painel desligado; atalho salvo como tecla (no Mac só clique); depois de
atualizar, a permissão "não pega" — em *Acessibilidade*, selecione Lotus,
clique em **−**, depois em **+** e escolha `/Applications/Lotus.app`; Lotus
aberto de dentro do `.dmg` ou de Downloads — mova para *Aplicativos*.

## Impressão 3D

- Tudo em **milímetros**, como nos fatiadores (Cura, PrusaSlicer, Bambu
  Studio, Orca). STL e OBJ não guardam unidade; 3MF é convertido; GLB é em
  metros e vira mm.
- **SVG → STL/3MF:** as áreas **preenchidas** viram peça (2 mm por padrão;
  `--espessura`, `--largura`); furos do desenho continuam furos.
- **Foto → litofania:** escuro fica mais grosso; 100 mm de largura, de 0,8 a
  3,0 mm. Imprima em branco, de pé, com 100% de preenchimento, e veja contra a
  luz. `--modo relevo` faz o contrário (claro = alto).
- Avisos quando algo se perde: peças unidas, cores, malha aberta (o fatiador
  costuma reparar).
- **Fora do Lotus:** fatiar (G-code) é com o seu fatiador; STEP, com o seu
  programa de CAD.

## Comportamentos importantes

- O arquivo original **nunca** é alterado. Se o destino já existe, o novo
  recebe ` (1)`, ` (2)`… (a menos que você marque *Sobrescrever*).
- O formato é identificado pelo **conteúdo**: um JPG renomeado para `.png` é
  tratado como JPG (com aviso).
- A saída é reaberta e conferida antes de ser salva; se estiver corrompida,
  nada é gravado.
- Sempre que algo se perde, o Lotus avisa: transparência → fundo branco, só
  o 1º quadro de GIF, só a 1ª aba do XLSX em CSV/JSON, layout do Word no PDF
  simples, páginas lidas por OCR (confira nomes, números e acentos).
- **PDF → PNG/JPG** com várias páginas cria a pasta `<nome> - páginas PNG`.
  **PDF com senha** não é convertido; o Lotus explica como gerar uma cópia.
- **OCR:** no Windows, o português precisa estar instalado em *Configurações
  → Hora e idioma → Idioma*; sem ele o Lotus usa o idioma do Windows e avisa.
- **CSV:** valores ficam como texto (CEP `01234` não perde o zero); o CSV
  gerado usa `;` e UTF-8 com BOM, que o Excel em português abre direto.

## Atualizar

*Ferramentas → Procurar atualização…* mostra se há versão nova e o que mudou.
**Baixar e instalar** baixa o instalador do seu sistema, confere o SHA-256
publicado (se não bater, apaga e não instala) e pede para **Reiniciar
agora**: o Lotus fecha, instala por cima — sem desinstalar — e abre de novo,
com suas configurações intactas. Uma vez por mês ele só **pergunta** se você
quer procurar.

## Ajuda e problemas

- **Ajuda** dentro do app: *Ferramentas → Ajuda* ou **F1** (funciona sem
  internet).
- Cada erro diz **o que fazer** (arquivo aberto em outro programa, sem
  permissão, disco cheio…). Reparos automáticos, sempre avisados: imagem
  incompleta (converte a parte recuperável), destino em uso (salva com outro
  nome), menu do botão direito desatualizado (corrigido ao abrir o Lotus).
- *Ferramentas → Diagnosticar e reparar* (ou `conversor-cli.exe --reparar`).
- Log local em `%LOCALAPPDATA%\Lotus\lotus.log` (Mac:
  `~/Library/Logs/Lotus/lotus.log`); *Ferramentas → Abrir pasta do log*.

## ffmpeg (áudio e vídeo)

O ffmpeg não vem junto; sem ele só as conversões de mídia ficam
indisponíveis. **Windows:** `winget install Gyan.FFmpeg` (ou coloque
`ffmpeg.exe` e `ffprobe.exe` numa pasta `ffmpeg\` ao lado do `Lotus.exe`, ou
defina `CONVERSOR_FFMPEG`). **Mac:** `brew install ffmpeg` (para OGG de
melhor qualidade, `brew install ffmpeg-full`).

## Privacidade (LGPD)

As conversões são 100% locais: o Lotus não envia arquivos, não coleta dados
e não tem telemetria.

**Única exceção, só quando você pede: "Procurar atualização".** O Lotus
consulta a página de versões no GitHub e, se você aceitar, baixa o
instalador. Nenhum dado seu é enviado; o GitHub (Microsoft) recebe apenas o
seu endereço IP, como em qualquer site. O lembrete mensal só pergunta.

O painel flutuante percebe o atalho pelos botões do mouse e pelas teclas
Ctrl/Shift/Alt/Win no momento do clique; **não lê o que você digita**. No
Windows, o vidro "fotografa" só a área onde o painel vai aparecer, só na
memória, para desfocar — nada é gravado nem enviado. O log fica só no seu
computador e pode ser apagado.

## Limitações

- PDF idêntico ao Word/PowerPoint exige o programa instalado (Windows); sem
  ele o Lotus faz um PDF simples e avisa. PDF → DOCX só com o Word.
- OCR existe no Windows 10/11 e no Mac (no Linux, não).
- G-code e STEP não são convertidos (use o fatiador e o CAD).
- Sem assinatura paga (Microsoft/Apple): avisos de segurança na 1ª abertura,
  e no Mac a permissão de Acessibilidade pode precisar ser refeita após
  atualizar.

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q               # Linux: xvfb-run -a python -m pytest -q
python -m conversor               # abre a interface
```

Instaladores e `.dmg` são gerados e testados pelo GitHub Actions
(`.github/workflows/ci.yml`) em Windows, Mac Apple Silicon e Mac Intel,
inclusive o programa empacotado, a instalação por cima (atualização) e a
desinstalação. Para gerar localmente no Windows:

```
pyinstaller --windowed --onedir --name Lotus --exclude-module pillow_heif --collect-data trimesh --collect-data reportlab --collect-data ezdxf --paths . packaging/app_gui.py
pyinstaller --console --onefile --name conversor-cli --exclude-module pillow_heif --collect-data trimesh --collect-data reportlab --collect-data ezdxf --paths . packaging/app_cli.py
```

O `pillow-heif` e o `python-docx` (em `requirements-dev.txt`) são só para os
testes. Licenças de terceiros: [docs/LICENCAS.md](docs/LICENCAS.md). Regras
do projeto e por que ele é assim: [CLAUDE.md](CLAUDE.md) e
[docs/ANALISE.md](docs/ANALISE.md).
