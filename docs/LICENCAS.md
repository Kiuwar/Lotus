# Licenças de terceiros

O Lotus é distribuído com as bibliotecas abaixo (versões fixadas em
`requirements.txt`). Esta lista cobre as que têm obrigação de aviso além de
manter o texto da licença.

## pi-heif (leitura de HEIC/HEIF)

- Pacote Python `pi-heif` 1.4.0 — licença BSD-3-Clause.
- Bibliotecas nativas embutidas no pacote, distribuídas como arquivos
  separados (`.dll` no Windows, `.dylib` no Mac) e carregadas dinamicamente:
  - **libheif** — LGPL-3.0 — código-fonte: <https://github.com/strukturag/libheif>
  - **libde265** (decodificador HEVC) — LGPL-3.0 — código-fonte:
    <https://github.com/strukturag/libde265>
- O arquivo `LICENSES_bundled.txt` do próprio pacote cita libheif 1.18.1 e
  libde265 1.0.15; a biblioteca instalada informa em tempo de execução
  (`pi_heif.libheif_info()`) libheif 1.23.0 e libde265 1.1.0. Os links acima
  levam ao repositório oficial de cada uma, onde estão todas as versões.
- LGPL: você pode substituir essas bibliotecas por outra versão compatível
  trocando os arquivos `libheif*` e `libde265*` dentro da pasta do Lotus.
- O pacote **não** inclui codificador HEVC (x265, GPL). Por isso o Lotus só
  lê HEIC; não grava.

## Impressão 3D e desenhos

trimesh (MIT), numpy (BSD-3 e outras permissivas), networkx (BSD-3), lxml (BSD-3),
shapely (BSD-3; inclui a GEOS, LGPL-2.1, como biblioteca separada), mapbox-earcut
(ISC), svgelements (MIT), resvg-py (MIT; inclui o resvg, Apache-2.0/MIT),
svglib (LGPL-3.0), reportlab (BSD), ezdxf (MIT).

## Ferramenta de testes (não vai no app)

- `pillow-heif` — usado só nos testes para criar amostras HEIC. Traz o x265
  (GPL) e é excluído do empacotamento (`--exclude-module pillow_heif`).

## Demais bibliotecas

Pillow (MIT-CMU), openpyxl (MIT), fpdf2 (LGPL-3.0), Markdown (BSD-3),
pypdf (BSD-3), pypdfium2 (BSD-3 / Apache-2.0), defusedxml (PSF),
pywin32 (PSF, só Windows), pyobjc (MIT, só Mac). O ffmpeg não é distribuído
com o Lotus: o usuário instala à parte.
