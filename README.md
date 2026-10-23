# Kiuwar Conversor

Aplicativo para Windows que converte arquivos entre formatos **no seu
computador**, sem enviar nada para a internet.

- Imagens: PNG, JPG, WEBP, BMP, GIF, TIFF, ICO (entre si e para PDF)
- Dados: CSV, JSON, XLSX (entre si)
- Documentos: TXT → PDF, Markdown → HTML
- Áudio e vídeo (com ffmpeg): MP3, WAV, OGG, FLAC, M4A, MP4, MKV, WEBM, AVI, MOV

Lista completa e sempre atualizada: [docs/FORMATOS.md](docs/FORMATOS.md)
(gerada a partir do código; 122 conversões, todas testadas).

## Como usar

**Interface:** abra `KiuwarConversor.exe`, clique em *Adicionar arquivos…*,
escolha o formato em *Converter para* e clique em *Converter*. O menu só
mostra formatos que servem para **todos** os arquivos selecionados.

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

## ffmpeg (áudio e vídeo)

O ffmpeg não vem embutido. Sem ele, as conversões de mídia ficam
indisponíveis (o restante funciona). Para ativar, faça **uma** das opções:

1. instale pelo winget (`winget search ffmpeg` mostra os pacotes; um
   comum é `Gyan.FFmpeg`) ou baixe de https://ffmpeg.org/download.html e
   coloque a pasta `bin` no PATH;
2. coloque `ffmpeg.exe` e `ffprobe.exe` numa pasta `ffmpeg\` ao lado do
   `KiuwarConversor.exe`;
3. defina a variável `CONVERSOR_FFMPEG` com o caminho do `ffmpeg.exe`.

## Privacidade (LGPD)

O processamento é 100% local: o aplicativo não faz conexões de rede, não
coleta dados e não tem telemetria. Os arquivos não saem do computador.

## Desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python -m conversor               # abre a interface
```

O executável para Windows é gerado pelo GitHub Actions
(`.github/workflows/ci.yml`, artefato **KiuwarConversor-windows**), que
também testa o `.exe` empacotado antes de publicá-lo. Para gerar localmente
no Windows:

```
pyinstaller --windowed --onedir --name KiuwarConversor --paths . packaging/app_gui.py
pyinstaller --console --onefile --name conversor-cli --paths . packaging/app_cli.py
```

Antes de pedir mudanças ao Claude, veja [CLAUDE.md](CLAUDE.md) e
[docs/ANALISE.md](docs/ANALISE.md).
