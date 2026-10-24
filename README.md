# Lotus

Converte arquivos entre formatos **no seu computador** (Windows e Mac),
sem enviar nada para a internet.

## Baixar

| Sistema | Arquivo |
|---|---|
| **Windows 10/11** | [**LotusSetup.exe**](https://github.com/Kiuwar/Lotus/releases/latest/download/LotusSetup.exe) |
| **Mac com chip Apple** (M1, M2, M3, M4…) | [**Lotus-Mac-AppleSilicon.dmg**](https://github.com/Kiuwar/Lotus/releases/latest/download/Lotus-Mac-AppleSilicon.dmg) |
| **Mac com processador Intel** | [**Lotus-Mac-Intel.dmg**](https://github.com/Kiuwar/Lotus/releases/latest/download/Lotus-Mac-Intel.dmg) |

Os links baixam sempre a versão mais nova, sem precisar de conta no GitHub.
Todas as versões, com o SHA-256 de cada arquivo:
[Releases](https://github.com/Kiuwar/Lotus/releases).

## O que converte

- **Imagens:** PNG, JPG, WEBP, BMP, GIF, TIFF, ICO e AVIF (entre si e para PDF)
- **Fotos do iPhone (HEIC/HEIF):** para JPG, PNG, PDF e as outras imagens
  (só leitura: o Lotus não grava HEIC)
- **PDF:** para imagens (PNG/JPG, uma por página) e para texto (TXT)
- **Word, sem precisar do Word:** DOCX → TXT, Markdown e HTML (títulos,
  listas, tabelas e links)
- **Word, com o Microsoft Word instalado (Windows):** DOCX, DOC, RTF e ODT
  entre si e para PDF e XPS; PDF → DOCX
- **PowerPoint, sem precisar do PowerPoint:** PPTX → TXT e Markdown (texto e
  notas de cada slide)
- **PowerPoint, com o PowerPoint instalado (Windows):** PPTX, PPT e ODP entre
  si e para PDF; uma imagem PNG/JPG por slide
- **Áudio (com ffmpeg):** MP3, WAV, OGG, FLAC, M4A, AAC, OPUS, WMA, AIFF;
  de qualquer vídeo também; áudio → MP4 (tela preta, para sites que só aceitam vídeo)
- **Vídeo (com ffmpeg):** MP4, MKV, WEBM, AVI, MOV, WMV, MPEG, M4V; vídeo →
  GIF animado e vídeo → imagem (PNG/JPG)
- **Dados e texto:** CSV, JSON, XLSX entre si; TXT → PDF; Markdown → HTML

Lista completa, gerada a partir do código: [docs/FORMATOS.md](docs/FORMATOS.md)
(334 conversões). As que não dependem do Word/PowerPoint são testadas de
verdade no CI (Windows, Mac e Linux); as do Word/PowerPoint, com o programa
simulado — o CI não tem Office.

## Instalar no Windows

1. Baixe o [**LotusSetup.exe**](https://github.com/Kiuwar/Lotus/releases/latest/download/LotusSetup.exe).
2. Execute o `LotusSetup.exe`. Não precisa de administrador: instala só
   para o seu usuário em `%LOCALAPPDATA%\Programs\Lotus`.
3. Como o instalador não tem assinatura digital, o Windows SmartScreen pode
   mostrar "O Windows protegeu o computador". Clique em *Mais informações* →
   *Executar assim mesmo*.
4. Na instalação você escolhe: menu do botão direito, painel flutuante
   (Ctrl+Shift+clique), **ícone ao lado do relógio** e atalho na área de
   trabalho.

Para remover: *Configurações → Aplicativos → Lotus → Desinstalar*. Isso
também remove o menu, o painel flutuante e o início automático. Sua
configuração (`%APPDATA%\Lotus`) e os arquivos convertidos são mantidos.

## Instalar no Mac

1. Na página **Releases**, baixe o `.dmg` do seu Mac:
   - **Lotus-Mac-AppleSilicon.dmg** para Macs com chip M1, M2, M3, M4…
   - **Lotus-Mac-Intel.dmg** para Macs com processador Intel.
   (Menu  → Sobre Este Mac → "Chip" ou "Processador".)
2. Abra o `.dmg` e arraste o **Lotus** para **Aplicativos**.
3. Na 1ª abertura o macOS bloqueia apps sem assinatura paga da Apple:
   **Ajustes do Sistema → Privacidade e Segurança → Abrir Mesmo Assim**.
4. Para o painel por atalho (⌥ Option+⇧ Shift+clique): **Ajustes do
   Sistema → Privacidade e Segurança → Acessibilidade → ative o Lotus**.
   Na primeira vez que o painel ler os arquivos selecionados, o Mac pede
   para o Lotus controlar o **Finder**: clique em **Permitir**.
5. Clique direito: *Ferramentas → Instalar Ação Rápida do Finder*; depois,
   no Finder, clique direito num arquivo → **Ações Rápidas → Converter com
   Lotus**.

No Mac a janela usa a moldura nativa do sistema (já arredondada, com as
bolinhas). Conversões pelo Microsoft Word (DOCX↔PDF) existem só no Windows.

## Como usar

**Interface:** abra `Lotus.exe`, clique em *Adicionar arquivos…*,
escolha o formato em *Converter para* e clique em *Converter*. O menu só
mostra formatos que servem para **todos** os arquivos selecionados.

**Botão direito do mouse:** no menu *Ferramentas* do Lotus, clique em
*Instalar menu do botão direito* (ou rode `conversor-cli.exe --instalar-menu`).
Depois, clique com o botão direito em qualquer arquivo suportado →
**Converter para** → escolha o formato. A conversão acontece na hora e um
aviso aparece no canto da tela. O item **Escolher formato…** abre uma
janela com um botão para cada formato possível.

- No **Windows 11**, o item fica em *Mostrar mais opções* (ou Shift+F10).
  O menu novo do Windows 11 só aceita extensões empacotadas como MSIX.
- Não precisa de administrador: é instalado só para o seu usuário.
- Para remover: *Ferramentas → Remover menu do botão direito*.
- Com vários arquivos selecionados, o Explorer abre uma conversão por
  arquivo (um aviso para cada um).

**Painel flutuante (Ctrl+Shift+clique):** numa pasta do Explorer **ou na
área de trabalho**, segure **Ctrl+Shift** e clique num arquivo: aparece, em
volta do cursor, um painel redondo com os formatos **separados por grupo**
(Imagem, Documento, Texto e dados, Áudio, Vídeo), cada um num arco colorido
próprio. Passe o mouse para destacar e clique para converter: a caixa mostra
"…" e depois ✓ (ou ✕ com a explicação). O painel some sozinho após o ✓, com
*Esc*, clicando fora, clicando no centro ou após 15 s sem uso. Com mais de 12
formatos, a caixa **Mais…** abre a lista completa.

- O atalho é configurável em *Ferramentas → Atalho do painel flutuante…*:
  qualquer combinação de Ctrl/Shift/Alt/Win com qualquer botão do mouse
  (esquerdo, direito, meio, laterais) **ou** com uma tecla (A–Z, 0–9,
  F1–F24). Com tecla, o painel atua nos arquivos já selecionados.
- O app recusa atalhos que travariam o uso normal (ex.: clique esquerdo sem
  nenhuma tecla) e avisa sobre conflitos (ex.: Ctrl+clique, que o Windows
  usa para selecionar vários arquivos).
- Na área de trabalho, só vale o clique **sobre os ícones**.
- Roda em segundo plano (processo `Lotus.exe`) e inicia com o Windows
  enquanto estiver ligado. Para desligar: desmarque a opção na mesma janela.

**Ícone ao lado do relógio (Windows):** a flor do Lotus fica na área de
notificação, ao lado do relógio, desde que o Windows inicia.
- **Duplo clique:** abre o Lotus.
- **Clique direito:** *Converter arquivos…*, ligar/desligar o *Painel por
  atalho*, *Configurar atalho…*, *Aparência…* e *Fechar o Lotus* (ele volta
  ao ligar o computador).
- O Windows escolhe se o ícone aparece na barra ou dentro da setinha **^**:
  nenhum programa pode forçar isso. Para deixá-lo sempre visível, arraste o
  ícone para fora da setinha, ou ligue-o em *Configurações → Personalização
  → Barra de tarefas → Selecionar quais ícones aparecem na barra de tarefas*.
- Para desligar ou religar: no Lotus, *Ferramentas → Ícone ao lado do relógio*.

**Aparência (Ferramentas → Aparência…):** estilo macOS, com prévia ao vivo.
- Temas prontos: **Sistema, Grafite, Azul Mac, Rosa, Verde**.
- Claro/escuro: segue o Windows ou fixo.
- Cores: destaque, fundo e **uma cor por grupo** de formatos.
- Tamanho (pequeno/médio/grande), opacidade do fundo (60–100%) e forma
  (radial ou cartão em lista).
- A janela principal tem moldura própria com cantos arredondados e as
  "bolinhas" de fechar/minimizar/maximizar. Se preferir a moldura padrão do
  Windows, há uma opção na mesma janela.

**Linha de comando:**

```
conversor-cli.exe foto.png planilha.csv --para pdf
conversor-cli.exe dados.json --para xlsx --saida C:\Saida
conversor-cli.exe --listar
```

## Comportamentos importantes

- **PDF → PNG/JPG:** PDF de 1 página vira um arquivo; com várias páginas, o
  Lotus cria a pasta `<nome> - páginas PNG` com `pagina_001.png`, `pagina_002.png`…
- **PDF → TXT:** só funciona com PDF que tem texto selecionável. PDF escaneado
  (foto de papel) não tem texto e o Lotus avisa — ainda não há OCR.
- **PDF com senha:** não é convertido; o Lotus explica como gerar uma cópia sem senha.
- **Word:** DOCX → PDF e PDF → DOCX usam o Microsoft Word do seu computador
  (sem Word, essas opções aparecem como indisponíveis). No PDF → DOCX o
  layout é reconstruído pelo Word e pode mudar: confira o documento.
- Se um arquivo não tem conversão, a coluna *Situação* e a área ao lado de
  "Converter para" dizem o motivo.

- O arquivo original **nunca** é alterado.
- Se o destino já existe, o novo recebe ` (1)`, ` (2)`… (a menos que você
  marque *Sobrescrever*).
- O formato é identificado pelo **conteúdo**: um JPG renomeado para `.png` é
  tratado como JPG (com aviso).
- A saída é reaberta e validada antes de ser salva; se estiver corrompida,
  nada é gravado e o erro aparece.
- Avisos aparecem sempre que algo se perde: transparência → fundo branco em
  JPG/BMP/PDF, só o 1º quadro de GIF animado, só a 1ª planilha do XLSX.
- CSV: valores ficam como **texto** (CEP `01234` não perde o zero). O CSV
  gerado usa `;` e UTF-8 com BOM, o que o Excel em português abre direto.
  Textos começando com `=` são gravados no XLSX como texto, não como fórmula.

## Quando algo dá errado (reparação de erros)

- **Mensagens com solução:** arquivo aberto em outro programa, sem
  permissão, disco cheio, memória insuficiente — cada erro diz o que fazer.
- **Reparo automático, sempre com aviso:**
  - imagem danificada/incompleta (download interrompido): a parte
    recuperável é convertida;
  - destino aberto em outro programa (ex.: Excel) com *Sobrescrever*
    marcado: salva com outro nome em vez de perder a conversão;
  - menu do botão direito desatualizado (o Lotus mudou de pasta): é
    corrigido sozinho ao abrir o Lotus.
- **Ferramentas → Diagnosticar e reparar** (ou `conversor-cli.exe --reparar`):
  confere o menu, o ffmpeg e as pastas de log/temporária, e corrige o menu.
- **Log local:** detalhes técnicos ficam em `%LOCALAPPDATA%\Lotus\lotus.log`
  (*Ferramentas → Abrir pasta do log*). Nunca é enviado a lugar nenhum.

O que **não** é "reparado" de propósito: dados de planilha/JSON inválidos
não são corrigidos por adivinhação, porque isso poderia mudar o conteúdo
sem você perceber.

## ffmpeg (áudio e vídeo)

O ffmpeg não vem embutido. Sem ele, as conversões de mídia ficam
indisponíveis (o restante funciona). Para ativar, faça **uma** das opções:

1. instale pelo winget (`winget search ffmpeg` mostra os pacotes; um
   comum é `Gyan.FFmpeg`) ou baixe de https://ffmpeg.org/download.html e
   coloque a pasta `bin` no PATH;
2. coloque `ffmpeg.exe` e `ffprobe.exe` numa pasta `ffmpeg\` ao lado do
   `Lotus.exe`;
3. defina a variável `CONVERSOR_FFMPEG` com o caminho do `ffmpeg.exe`.

No Mac: `brew install ffmpeg` (Homebrew). Esse pacote não traz mais o
codificador libvorbis; o Lotus então gera OGG com o codificador Vorbis
interno do ffmpeg (estéreo, qualidade um pouco menor) e avisa. Para a
melhor qualidade em OGG: `brew install ffmpeg-full`.

## Privacidade (LGPD)

O processamento é 100% local: o aplicativo não faz conexões de rede, não
coleta dados e não tem telemetria. Os arquivos não saem do computador.

O painel flutuante usa um "gancho de mouse" do Windows para perceber o
atalho. Ele só olha botões do mouse e o estado de Ctrl/Shift/Alt/Win no
momento do clique; **não lê o que você digita**, não grava e não envia
nada. Quando o atalho é uma tecla, o Windows avisa o Lotus apenas daquela
combinação (RegisterHotKey). Alguns antivírus desconfiam de programas com
gancho de mouse; se o seu bloquear, é esse o motivo.
O log de erros fica só no seu computador e contém nomes de arquivos; pode
ser apagado a qualquer momento.

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m conversor               # abre a interface
```

O executável para Windows é gerado pelo GitHub Actions
(`.github/workflows/ci.yml`, artefato **Lotus-windows**), que
também testa o `.exe` empacotado antes de publicá-lo. Para gerar localmente
no Windows:

```
pyinstaller --windowed --onedir --name Lotus --exclude-module pillow_heif --paths . packaging/app_gui.py
pyinstaller --console --onefile --name conversor-cli --exclude-module pillow_heif --paths . packaging/app_cli.py
```

O `pillow-heif` (em `requirements-dev.txt`) só cria as amostras HEIC dos
testes; ele traz o codificador x265 (GPL) e é excluído do app empacotado.
Licenças de terceiros: [docs/LICENCAS.md](docs/LICENCAS.md).

Antes de pedir mudanças ao Claude, veja [CLAUDE.md](CLAUDE.md) e
[docs/ANALISE.md](docs/ANALISE.md).
