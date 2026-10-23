# Lotus

Uma ferramenta para converter arquivos pelo computador: aplicativo para Windows que converte arquivos entre formatos **no seu
computador**, sem enviar nada para a internet.

- Imagens: PNG, JPG, WEBP, BMP, GIF, TIFF, ICO (entre si e para PDF)
- Dados: CSV, JSON, XLSX (entre si)
- Documentos: TXT → PDF, Markdown → HTML
- Áudio e vídeo (com ffmpeg): MP3, WAV, OGG, FLAC, M4A, MP4, MKV, WEBM, AVI, MOV

Lista completa e sempre atualizada: [docs/FORMATOS.md](docs/FORMATOS.md)
(gerada a partir do código; 122 conversões, todas testadas).

## Instalar no Windows

1. Baixe o **LotusSetup.exe** na página **Releases** do repositório
   (coluna da direita da página inicial, ou a aba *Code → Releases*), em
   *Assets*. Também fica como artefato **LotusSetup** em cada execução
   verde da aba *Actions* (vem em .zip; extraia; exige login no GitHub).
2. Execute o `LotusSetup.exe`. Não precisa de administrador: instala só
   para o seu usuário em `%LOCALAPPDATA%\Programs\Lotus`.
3. Como o instalador não tem assinatura digital, o Windows SmartScreen pode
   mostrar "O Windows protegeu o computador". Clique em *Mais informações* →
   *Executar assim mesmo*.
4. Na instalação você escolhe: menu do botão direito, painel flutuante
   (Ctrl+Shift+clique) e atalho na área de trabalho.

Para remover: *Configurações → Aplicativos → Lotus → Desinstalar*. Isso
também remove o menu, o painel flutuante e o início automático. Sua
configuração (`%APPDATA%\Lotus`) e os arquivos convertidos são mantidos.

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

**Painel flutuante (Ctrl+Shift+clique):** numa janela do Explorer, segure
**Ctrl+Shift** e clique num arquivo: aparece, junto do cursor, um painel com
um botão para cada formato possível. Clique no formato e pronto. *Esc* fecha.

- O atalho é configurável em *Ferramentas → Atalho do painel flutuante…*:
  qualquer combinação de Ctrl/Shift/Alt/Win com qualquer botão do mouse
  (esquerdo, direito, meio, laterais) **ou** com uma tecla (A–Z, 0–9,
  F1–F24). Com tecla, o painel atua nos arquivos já selecionados.
- O app recusa atalhos que travariam o uso normal (ex.: clique esquerdo sem
  nenhuma tecla) e avisa sobre conflitos (ex.: Ctrl+clique, que o Windows
  usa para selecionar vários arquivos).
- Funciona nas janelas de pastas do Explorer. **Não funciona na área de
  trabalho** nem dentro de outros programas (lá o clique segue normal).
- Roda em segundo plano (processo `Lotus.exe`) e inicia com o Windows
  enquanto estiver ligado. Para desligar: desmarque a opção na mesma janela.

**Linha de comando:**

```
conversor-cli.exe foto.png planilha.csv --para pdf
conversor-cli.exe dados.json --para xlsx --saida C:\Saida
conversor-cli.exe --listar
```

## Comportamentos importantes

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
pyinstaller --windowed --onedir --name Lotus --paths . packaging/app_gui.py
pyinstaller --console --onefile --name conversor-cli --paths . packaging/app_cli.py
```

Antes de pedir mudanças ao Claude, veja [CLAUDE.md](CLAUDE.md) e
[docs/ANALISE.md](docs/ANALISE.md).
