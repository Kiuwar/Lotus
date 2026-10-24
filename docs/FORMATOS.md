# Formatos suportados

<!-- Arquivo GERADO por scripts/gerar_formatos.py. Não edite à mão. -->

Total: **372 conversões**, todas cobertas por tests/test_matrix.py.

## Apresentação

| Origem | Destinos |
|---|---|
| PPTX | MD, TXT |

Observação: Texto e notas de cada slide (sem PowerPoint); imagens e layout não.

## Dados

| Origem | Destinos |
|---|---|
| CSV | JSON, XLSX |
| JSON | CSV, XLSX |
| XLSX | CSV, JSON |

## Documento

| Origem | Destinos |
|---|---|
| DOC | HTML, TXT |
| DOCX | HTML, MD, TXT |
| HTML | DOCX, MD, PDF, TXT |
| MD | DOCX, HTML, PDF, TXT |
| ODT | HTML, TXT |
| RTF | HTML, TXT |
| TXT | DOCX, PDF |

Observação: Markdown com tabelas e blocos de código.

Observação: Requer o textutil do macOS (só no Mac).

Observação: Sem Word: títulos, listas, tabelas e links; layout simples em A4.

Observação: Sem Word: títulos, listas, tabelas, links e negrito/itálico viram estilos do Word.

Observação: Só o texto e a estrutura da página.

Observação: Texto simples, A4, fonte 11.

Observação: Texto, títulos, listas, tabelas e links (sem Word); fontes, cores e imagens não.

Observação: Tira a marcação; mantém listas e tabelas.

## Imagem

| Origem | Destinos |
|---|---|
| AVIF | BMP, GIF, ICO, JPG, PDF, PNG, TIFF, WEBP |
| BMP | AVIF, GIF, ICO, JPG, PDF, PNG, TIFF, WEBP |
| GIF | AVIF, BMP, ICO, JPG, PDF, PNG, TIFF, WEBP |
| HEIC | AVIF, BMP, GIF, ICO, JPG, PDF, PNG, TIFF, WEBP |
| ICO | AVIF, BMP, GIF, JPG, PDF, PNG, TIFF, WEBP |
| JPG | AVIF, BMP, GIF, ICO, PDF, PNG, TIFF, WEBP |
| PNG | AVIF, BMP, GIF, ICO, JPG, PDF, TIFF, WEBP |
| TIFF | AVIF, BMP, GIF, ICO, JPG, PDF, PNG, WEBP |
| WEBP | AVIF, BMP, GIF, ICO, JPG, PDF, PNG, TIFF |

Observação: HEIC/HEIF só como origem (fotos do iPhone); gravar HEIC não é oferecido.

Observação: Requer Pillow com suporte a AVIF (incluído no instalador).

Observação: Uma página por imagem.

## PDF

| Origem | Destinos |
|---|---|
| PDF | JPG, PNG, TXT |

Observação: Só o texto (sem layout). PDF escaneado não tem texto e não há OCR.

Observação: Uma imagem por página (150 DPI); várias páginas vão para uma pasta.

## PowerPoint

| Origem | Destinos |
|---|---|
| ODP | JPG, PDF, PNG, PPT, PPTX |
| PPT | JPG, ODP, PDF, PNG, PPTX |
| PPTX | JPG, ODP, PDF, PNG, PPT |

Observação: Requer o Microsoft PowerPoint instalado neste computador.

Observação: Uma imagem por slide (1920 px de largura). Requer o Microsoft PowerPoint instalado neste computador.

## Vídeo

| Origem | Destinos |
|---|---|
| AAC | MP4 |
| AIFF | MP4 |
| AVI | GIF, JPG, M4V, MKV, MOV, MP4, MPEG, PNG, WEBM, WMV |
| FLAC | MP4 |
| M4A | MP4 |
| M4V | AVI, GIF, JPG, MKV, MOV, MP4, MPEG, PNG, WEBM, WMV |
| MKV | AVI, GIF, JPG, M4V, MOV, MP4, MPEG, PNG, WEBM, WMV |
| MOV | AVI, GIF, JPG, M4V, MKV, MP4, MPEG, PNG, WEBM, WMV |
| MP3 | MP4 |
| MP4 | AVI, GIF, JPG, M4V, MKV, MOV, MPEG, PNG, WEBM, WMV |
| MPEG | AVI, GIF, JPG, M4V, MKV, MOV, MP4, PNG, WEBM, WMV |
| OGG | MP4 |
| OPUS | MP4 |
| WAV | MP4 |
| WEBM | AVI, GIF, JPG, M4V, MKV, MOV, MP4, MPEG, PNG, WMV |
| WMA | MP4 |
| WMV | AVI, GIF, JPG, M4V, MKV, MOV, MP4, MPEG, PNG, WEBM |

Observação: Requer ffmpeg instalado (veja README, seção ffmpeg).

## Word

| Origem | Destinos |
|---|---|
| DOC | DOCX, ODT, PDF, RTF, XPS |
| DOCX | DOC, ODT, PDF, RTF, XPS |
| ODT | DOC, DOCX, PDF, RTF, XPS |
| PDF | DOCX |
| RTF | DOC, DOCX, ODT, PDF, XPS |

Observação: Com o Word: igual ao Word. Sem o Word: PDF simples (texto, títulos, listas, tabelas).

Observação: Requer o Microsoft Word (Windows) ou o textutil do macOS (já vem no Mac).

Observação: Requer o Microsoft Word (Windows) ou o textutil do macOS (já vem no Mac). No Mac o PDF é simples (texto, títulos, listas, tabelas).

Observação: Requer o Microsoft Word instalado neste computador.

## Áudio

| Origem | Destinos |
|---|---|
| AAC | AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| AIFF | AAC, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| AVI | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| FLAC | AAC, AIFF, M4A, MP3, OGG, OPUS, WAV, WMA |
| M4A | AAC, AIFF, FLAC, MP3, OGG, OPUS, WAV, WMA |
| M4V | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| MKV | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| MOV | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| MP3 | AAC, AIFF, FLAC, M4A, OGG, OPUS, WAV, WMA |
| MP4 | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| MPEG | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| OGG | AAC, AIFF, FLAC, M4A, MP3, OPUS, WAV, WMA |
| OPUS | AAC, AIFF, FLAC, M4A, MP3, OGG, WAV, WMA |
| WAV | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WMA |
| WEBM | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |
| WMA | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV |
| WMV | AAC, AIFF, FLAC, M4A, MP3, OGG, OPUS, WAV, WMA |

Observação: Requer ffmpeg instalado (veja README, seção ffmpeg).
