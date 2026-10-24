"""Testes de conteúdo: a saída precisa estar CERTA, não só existir."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image

from conversor.converters import media
from conversor.core import registry
from conversor.core.detect import DetectionError, detect
from conversor.core.engine import ConversionError, convert_file

from .conftest import HAS_FFMPEG


# ---------- dados ----------

def test_csv_to_xlsx_preserves_text_and_blocks_formulas(sample, tmp_path):
    from openpyxl import load_workbook

    out = convert_file(sample("csv"), "xlsx", out_dir=tmp_path).output
    ws = load_workbook(out).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0] == ["nome", "cep", "preço"]
    assert rows[1] == ["João", "01234-000", "10,50"]  # zero à esquerda e vírgula intactos
    assert ws["B3"].value == "=SOMA(1;2)"
    assert ws["B3"].data_type == "s", "texto com '=' não pode virar fórmula"


def test_json_to_csv_unions_keys_and_serialises_nested(sample, tmp_path):
    res = convert_file(sample("json"), "csv", out_dir=tmp_path)
    with open(res.output, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == ["nome", "cep", "itens", "idade"]
    assert rows[1] == ["João", "01234-000", "[1, 2]", ""]
    assert rows[2] == ["Ana", "", "", "30"]
    assert any("aninhados" in w for w in res.warnings)


def test_xlsx_to_json_keeps_types(sample, tmp_path):
    out = convert_file(sample("xlsx"), "json", out_dir=tmp_path).output
    assert json.loads(out.read_text(encoding="utf-8")) == [{"nome": "Café", "valor": 3.5}]


def test_csv_cp1252_is_decoded_with_warning(tmp_path):
    src = tmp_path / "antigo.csv"
    src.write_bytes("nome;cidade\nJosé;São Paulo\n".encode("cp1252"))
    res = convert_file(src, "json", out_dir=tmp_path)
    assert json.loads(res.output.read_text(encoding="utf-8")) == [
        {"nome": "José", "cidade": "São Paulo"}
    ]
    assert any("Windows-1252" in w for w in res.warnings)


def test_json_object_root_is_rejected_clearly(tmp_path):
    src = tmp_path / "obj.json"
    src.write_text('{"a": 1, "b": 2}', encoding="utf-8")
    with pytest.raises(ConversionError, match="lista de objetos"):
        convert_file(src, "csv", out_dir=tmp_path)


# ---------- imagens ----------

def test_png_with_alpha_to_jpg_flattens_on_white(tmp_path):
    src = tmp_path / "t.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(src)
    res = convert_file(src, "jpg", out_dir=tmp_path)
    with Image.open(res.output) as im:
        assert im.format == "JPEG"
        r, g, b = im.convert("RGB").getpixel((5, 5))
        assert min(r, g, b) > 245  # branco (JPEG tem pequena perda)
    assert any("transparência" in w for w in res.warnings)


def test_exif_orientation_is_applied(tmp_path):
    src = tmp_path / "foto.jpg"
    im = Image.new("RGB", (40, 20), "red")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotacionar 90° (padrão de celular em retrato)
    im.save(src, exif=exif)
    out = convert_file(src, "png", out_dir=tmp_path).output
    with Image.open(out) as o:
        assert o.size == (20, 40)


def test_animated_gif_warns_first_frame_only(tmp_path):
    src = tmp_path / "anim.gif"
    frames = [Image.new("RGB", (8, 8), c) for c in ("red", "blue")]
    frames[0].save(src, save_all=True, append_images=frames[1:])
    res = convert_file(src, "png", out_dir=tmp_path)
    assert any("2 quadros" in w for w in res.warnings)


def test_ico_contains_multiple_sizes(tmp_path):
    src = tmp_path / "logo.png"
    Image.new("RGBA", (256, 256), "green").save(src)
    out = convert_file(src, "ico", out_dir=tmp_path).output
    with Image.open(out) as im:
        assert {(16, 16), (32, 32), (256, 256)} <= set(im.info["sizes"])


# ---------- documentos ----------

def test_txt_to_pdf_keeps_accents(sample, tmp_path):
    from pypdf import PdfReader

    out = convert_file(sample("txt"), "pdf", out_dir=tmp_path).output
    text = "".join(p.extract_text() for p in PdfReader(out).pages)
    assert "ação" in text and "coração" in text


def test_md_to_html_renders_table(sample, tmp_path):
    html = convert_file(sample("md"), "html", out_dir=tmp_path).output.read_text(encoding="utf-8")
    assert "<h1>Título</h1>" in html and "<table>" in html and 'charset="utf-8"' in html


# ---------- segurança do motor ----------

def test_never_overwrites_by_default(sample, tmp_path):
    src = sample("png")
    a = convert_file(src, "jpg", out_dir=tmp_path).output
    b = convert_file(src, "jpg", out_dir=tmp_path).output
    assert a.name == "amostra.jpg" and b.name == "amostra (1).jpg"


def test_overwrite_when_asked(sample, tmp_path):
    src = sample("png")
    a = convert_file(src, "jpg", out_dir=tmp_path).output
    b = convert_file(src, "jpg", out_dir=tmp_path, overwrite=True).output
    assert a == b


def test_wrong_extension_uses_real_content(tmp_path):
    src = tmp_path / "mentira.png"
    Image.new("RGB", (8, 8)).save(src, format="JPEG")
    res = convert_file(src, "webp", out_dir=tmp_path)
    assert res.source_format == "jpg"
    assert any("conteúdo é JPG" in w for w in res.warnings)


def test_csv_starting_with_bm_is_still_csv(tmp_path):
    src = tmp_path / "carros.csv"
    src.write_text("BMW;Audi\n1;2\n", encoding="utf-8")
    assert detect(src).fmt == "csv"


def test_binary_with_text_extension_is_rejected(tmp_path):
    src = tmp_path / "x.txt"
    src.write_bytes(b"\x00\x01\x02garbage")
    with pytest.raises(DetectionError):
        detect(src)


def test_empty_file_is_rejected(tmp_path):
    src = tmp_path / "vazio.png"
    src.write_bytes(b"")
    with pytest.raises(ConversionError, match="vazio"):
        convert_file(src, "jpg")


def test_unsupported_pair_lists_alternatives(sample, tmp_path):
    with pytest.raises(ConversionError, match="não suportada.*PDF"):
        convert_file(sample("txt"), "xlsx", out_dir=tmp_path)


def test_same_format_is_rejected(sample, tmp_path):
    with pytest.raises(ConversionError, match="já está"):
        convert_file(sample("png"), "png", out_dir=tmp_path)


def test_failed_conversion_leaves_no_files(tmp_path):
    src = tmp_path / "quebrado.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"lixo" * 10)
    out = tmp_path / "out"
    with pytest.raises(ConversionError):
        convert_file(src, "jpg", out_dir=out)
    assert list(out.iterdir()) == []


def test_media_unavailable_without_ffmpeg(monkeypatch, tmp_path):
    media.ffmpeg_path.cache_clear()
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("CONVERSOR_FFMPEG", raising=False)
    try:
        assert "mp3" not in registry.targets_for("wav")
        src = tmp_path / "a.wav"
        src.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        with pytest.raises(ConversionError, match="componente ausente"):
            convert_file(src, "mp3", out_dir=tmp_path)
    finally:
        media.ffmpeg_path.cache_clear()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_video_to_audio_has_duration(sample, tmp_path):
    import subprocess

    out = convert_file(sample("mp4"), "mp3", out_dir=tmp_path).output
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert 0.5 < float(dur) < 2.0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_encoder_list_is_read_from_installed_ffmpeg():
    assert media.tem_codificador("flac") and media.tem_codificador("pcm_s16le")
    assert not media.tem_codificador("nao-existe")


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
@pytest.mark.parametrize("canais", [1, 6])
def test_ogg_without_libvorbis_uses_internal_encoder_and_warns(tmp_path, monkeypatch, canais):
    """ffmpeg do Homebrew sem libvorbis: OGG sai com o Vorbis interno, em estéreo, com aviso."""
    import subprocess

    src = tmp_path / f"tom{canais}.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-ac", str(canais), str(src)], check=True)
    real = media.tem_codificador
    monkeypatch.setattr(media, "tem_codificador", lambda n: n != "libvorbis" and real(n))

    r = convert_file(src, "ogg", out_dir=tmp_path)
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,channels:format=duration",
         "-of", "csv=p=0", str(r.output)], capture_output=True, text=True, check=True,
    ).stdout.split()
    assert info[0] == "vorbis,2"
    assert 0.5 < float(info[1]) < 2.0
    assert any("libvorbis" in w for w in r.warnings)


def _probe(path):
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,nb_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
@pytest.mark.parametrize("alvo,codec", [("aac", "aac"), ("opus", "opus"), ("wma", "wmav2"),
                                        ("aiff", "pcm_s16be")])
def test_new_audio_formats_have_right_codec_and_duration(sample, tmp_path, alvo, codec):
    r = convert_file(sample("mp3"), alvo, out_dir=tmp_path)
    info = _probe(r.output)
    assert [s["codec_name"] for s in info["streams"]] == [codec]
    assert 0.5 < float(info["format"]["duration"]) < 2.0
    assert detect(r.output).fmt == alvo, "o arquivo gerado é reconhecido pelo conteúdo"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
@pytest.mark.parametrize("alvo,codec_video", [("wmv", "wmv2"), ("mpeg", "mpeg2video"), ("m4v", "h264")])
def test_new_video_formats_keep_video_and_audio(sample, tmp_path, alvo, codec_video):
    r = convert_file(sample("mp4"), alvo, out_dir=tmp_path)
    tipos = {s["codec_type"]: s["codec_name"] for s in _probe(r.output)["streams"]}
    assert tipos.get("video") == codec_video and "audio" in tipos
    assert detect(r.output).fmt == alvo


@pytest.mark.parametrize("fps,taxa,aviso", [
    (25.0, None, False), (30000 / 1001, None, False), (10.0, "24000/1001", False),
    (15.0, "24000/1001", False), (26.0, "30000/1001", False), (120.0, "60", True), (None, None, False),
])
def test_mpeg2_frame_rate_rule(fps, taxa, aviso):
    r, a = media.fps_mpeg2(fps)
    assert r == taxa and bool(a) is aviso


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_mpeg_from_nonstandard_frame_rate_uses_a_standard_one(sample, tmp_path):
    src = sample("mp4")  # 10 quadros/s
    r = convert_file(src, "mpeg", out_dir=tmp_path)
    import subprocess

    taxa = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                           "stream=r_frame_rate", "-of", "csv=p=0", str(r.output)],
                          capture_output=True, text=True, check=True).stdout.strip().rstrip(",")
    assert taxa == "24000/1001"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_video_to_gif_is_animated_and_warns_about_sound(sample, tmp_path):
    r = convert_file(sample("mp4"), "gif", out_dir=tmp_path)
    with Image.open(r.output) as g:
        assert g.n_frames >= 5 and g.width <= 480
    assert any("não tem som" in w for w in r.warnings)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
@pytest.mark.parametrize("alvo", ["png", "jpg"])
def test_video_frame_is_an_image_of_the_video_size(sample, tmp_path, alvo):
    r = convert_file(sample("mp4"), alvo, out_dir=tmp_path)
    with Image.open(r.output) as im:
        assert im.size == (64, 48)
        cores = im.convert("RGB").getcolors(64 * 48)
        assert cores is None or len(cores) > 5, "quadro de teste colorido, não uma imagem lisa"
    assert any("única imagem" in w for w in r.warnings)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_audio_to_mp4_has_black_video_and_the_audio(sample, tmp_path):
    r = convert_file(sample("mp3"), "mp4", out_dir=tmp_path)
    info = _probe(r.output)
    tipos = {s["codec_type"]: s["codec_name"] for s in info["streams"]}
    assert tipos == {"video": "h264", "audio": "aac"}
    assert 0.5 < float(info["format"]["duration"]) < 2.0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_video_without_audio_explains_instead_of_failing_obscurely(tmp_path):
    import subprocess

    mudo = tmp_path / "mudo.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=64x48:rate=10:duration=1", "-pix_fmt", "yuv420p", str(mudo)],
                   check=True)
    with pytest.raises(ConversionError, match="não tem faixa de áudio"):
        convert_file(mudo, "mp3", out_dir=tmp_path / "out")


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_opus_without_libopus_uses_internal_encoder_and_warns(sample, tmp_path, monkeypatch):
    real = media.tem_codificador
    monkeypatch.setattr(media, "tem_codificador", lambda n: n != "libopus" and real(n))
    r = convert_file(sample("wav"), "opus", out_dir=tmp_path)
    assert [s["codec_name"] for s in _probe(r.output)["streams"]] == ["opus"]
    assert any("libopus" in w for w in r.warnings)


@pytest.mark.parametrize("nome,conteudo,esperado", [
    ("a.aiff", b"FORM\x00\x00\x00\x10AIFFCOMM", "aiff"),
    ("a.aif", b"FORM\x00\x00\x00\x10AIFFCOMM", "aiff"),
    ("a.wma", bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c") + b"\x00" * 8, "wma"),
    ("a.wmv", bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c") + b"\x00" * 8, "wmv"),
    ("a.mpg", b"\x00\x00\x01\xba" + b"\x00" * 12, "mpeg"),
    ("a.aac", b"\xff\xf1\x50\x40" + b"\x00" * 12, "aac"),
    ("a.opus", b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 4, "opus"),
    ("a.ogg", b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 4, "ogg"),  # Opus em .ogg vale
])
def test_new_media_formats_are_detected_by_content(tmp_path, nome, conteudo, esperado):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    assert detect(p).fmt == esperado


@pytest.mark.parametrize(
    "text,expected",
    [
        ("a;b;c\n1;2,5;3\n4;5,5;6\n", ";"),
        ("a,b,c\n1,2.5,3\n", ","),
        ("a\tb\n1\t2\n", "\t"),
        ('a,b\n"x;y",2\n', ","),
    ],
)
def test_guess_delimiter(text, expected):
    from conversor.converters.data import guess_delimiter

    assert guess_delimiter(text) == expected


# ---------- HEIC (fotos do iPhone) e AVIF ----------

def _ftyp(principal: bytes, compativeis: list[bytes]) -> bytes:
    corpo = principal + b"\x00\x00\x00\x00" + b"".join(compativeis)
    return (8 + len(corpo)).to_bytes(4, "big") + b"ftyp" + corpo + b"\x00" * 16


@pytest.mark.parametrize("principal,compativeis,esperado", [
    (b"heic", [b"mif1", b"heic"], "heic"),   # iPhone
    (b"mif1", [b"mif1", b"heic"], "heic"),   # HEIF genérico com HEVC
    (b"avif", [b"avif", b"mif1"], "avif"),
    (b"mif1", [b"mif1", b"avif"], "avif"),
    (b"isom", [b"isom", b"mp41"], "mp4"),    # vídeo continua vídeo
    (b"M4A ", [b"M4A "], "m4a"),
])
def test_heif_family_is_told_apart_from_video_by_brand(tmp_path, principal, compativeis, esperado):
    p = tmp_path / "arquivo.bin"
    p.write_bytes(_ftyp(principal, compativeis))
    from conversor.core.detect import sniff

    assert sniff(p) == esperado


def test_heic_with_wrong_extension_is_still_heic(tmp_path):
    from .conftest import make_heic

    p = make_heic(tmp_path / "foto.jpg", [Image.new("RGB", (8, 8), "red")])
    assert detect(p).fmt == "heic"
    assert detect(make_heic(tmp_path / "foto.HEIF", [Image.new("RGB", (8, 8), "red")])).fmt == "heic"


def test_heic_photo_to_jpg_keeps_size_and_colors(tmp_path):
    from .conftest import make_heic

    foto = Image.new("RGB", (64, 48), (220, 30, 30))
    foto.paste((30, 30, 220), (32, 0, 64, 48))  # metade direita azul
    src = make_heic(tmp_path / "IMG_0001.HEIC", [foto])
    res = convert_file(src, "jpg", out_dir=tmp_path / "o")
    with Image.open(res.output) as im:
        assert im.format == "JPEG" and im.size == (64, 48)
        r, g, b = im.convert("RGB").getpixel((8, 24))
        assert r > 180 and g < 70 and b < 70, "metade esquerda vermelha"
        r, g, b = im.convert("RGB").getpixel((56, 24))
        assert b > 180 and r < 70 and g < 70, "metade direita azul"
    assert not res.warnings


def test_heic_with_several_images_warns_first_only(tmp_path):
    from .conftest import make_heic

    src = make_heic(tmp_path / "rajada.heic", [Image.new("RGB", (16, 16), c) for c in ("red", "blue")])
    res = convert_file(src, "png", out_dir=tmp_path / "o")
    assert any("2 quadros" in w for w in res.warnings)
    with Image.open(res.output) as im:
        assert im.convert("RGB").getpixel((8, 8))[0] > 200, "o primeiro quadro (vermelho)"


def test_heic_is_never_offered_as_output():
    assert "heic" not in {c.target for c in registry.all_converters()}


def _avif_ok():
    from conversor.converters.images import avif_disponivel

    if not avif_disponivel():
        pytest.skip("Pillow sem AVIF nesta máquina")


def test_png_to_avif_and_back_keeps_transparency(tmp_path):
    _avif_ok()
    src = tmp_path / "logo.png"
    im = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    im.paste((0, 160, 60, 255), (0, 0, 20, 30))
    im.save(src)
    avif = convert_file(src, "avif", out_dir=tmp_path / "a").output
    with Image.open(avif) as a:
        assert a.format == "AVIF" and a.size == (40, 30)
    volta = convert_file(avif, "png", out_dir=tmp_path / "b").output
    with Image.open(volta) as v:
        v = v.convert("RGBA")
        assert v.getpixel((35, 15))[3] < 10, "lado transparente continua transparente"
        r, g, b, a = v.getpixel((5, 15))
        assert a > 245 and g > 130 and r < 40, "lado verde opaco"


def test_avif_to_pdf_flattens_with_warning(tmp_path, sample):
    _avif_ok()
    res = convert_file(sample("avif"), "pdf", out_dir=tmp_path / "o")
    assert res.output.read_bytes().startswith(b"%PDF-")
    assert any("transparência" in w for w in res.warnings)


# ---------- documentos sem Word (detalhes em test_docx_escrita.py) ----------

def test_txt_to_docx_content_is_read_back_by_independent_reader(sample, tmp_path):
    docx = pytest.importorskip("docx")
    out = convert_file(sample("txt"), "docx", out_dir=tmp_path / "o").output
    paragrafos = [p.text for p in docx.Document(str(out)).paragraphs]
    assert paragrafos[:2] == ["Olá, ação e coração.", "\tLinha com tab."]
    assert paragrafos[2] == "x" * 300


# ---------- planilhas → tabela (HTML, Markdown, PDF) ----------

def _planilha(path: Path) -> Path:
    import datetime as dt

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Custas"
    ws.append(["Item", "Valor", "Taxa", "Data", "Total"])
    ws.append(["Petição <inicial>", 10.5, 0.15, dt.date(2026, 10, 24), "=B2*2"])
    ws["C2"].number_format = "0%"
    ws.append(["Perícia | laudo", 1200, None, dt.datetime(2026, 1, 2, 14, 30), None])
    resumo = wb.create_sheet("Resumo")
    resumo.append(["Total", 1210.5])
    oculta = wb.create_sheet("Rascunho")
    oculta.sheet_state = "hidden"
    oculta.append(["anotação"])
    wb.save(path)
    return path


def test_xlsx_to_markdown_has_every_sheet_and_brazilian_formats(tmp_path):
    r = convert_file(_planilha(tmp_path / "custas.xlsx"), "md", out_dir=tmp_path / "o")
    md = r.output.read_text(encoding="utf-8")
    assert "## Custas" in md and "## Resumo" in md and "## Rascunho (oculta)" in md
    assert "| Petição \\<inicial\\> | 10,5 | 15% | 24/10/2026 |  |" in md
    assert "| Perícia \\| laudo | 1200 |  | 02/01/2026 14:30 |  |" in md
    assert "| Total | 1210,5 |" in md
    avisos = " ".join(r.warnings)
    assert "1 fórmula(s) sem resultado" in avisos and "Como resolver" in avisos
    assert "Rascunho" in avisos, "aba oculta incluída e avisada"


def test_xlsx_to_html_is_escaped_table_with_header(tmp_path):
    out = convert_file(_planilha(tmp_path / "custas.xlsx"), "html", out_dir=tmp_path / "o").output
    h = out.read_text(encoding="utf-8")
    assert "<th>Item</th><th>Valor</th>" in h
    assert "<td>Petição &lt;inicial&gt;</td>" in h and "<inicial>" not in h
    assert h.count("<table>") == 3


def test_csv_to_html_keeps_text_exactly(sample, tmp_path):
    h = convert_file(sample("csv"), "html", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert "<td>01234-000</td>" in h, "CEP continua texto (zero à esquerda)"
    assert "<td>=SOMA(1;2)</td>" in h and "<td>10,50</td>" in h
    assert "<th>preço</th>" in h


def test_spreadsheet_to_pdf_has_the_data(tmp_path):
    from pypdf import PdfReader

    out = convert_file(_planilha(tmp_path / "custas.xlsx"), "pdf", out_dir=tmp_path / "o").output
    paginas = PdfReader(str(out)).pages
    assert len(paginas) == 3, "uma página por aba"
    texto = paginas[0].extract_text()
    assert "Petição <inicial>" in texto and "15%" in texto and "24/10/2026" in texto


def test_huge_sheet_pdf_is_limited_with_warning(tmp_path, monkeypatch):
    from conversor.converters import tabelas

    monkeypatch.setattr(tabelas, "LIMITE_LINHAS_PDF", 3)
    src = tmp_path / "grande.csv"
    src.write_text("n;v\n" + "".join(f"{i};x\n" for i in range(10)), encoding="utf-8")
    r = convert_file(src, "pdf", out_dir=tmp_path / "o")
    assert any("10 linhas" in w and "HTML" in w for w in r.warnings)


def test_json_to_markdown_table(sample, tmp_path):
    md = convert_file(sample("json"), "md", out_dir=tmp_path / "o").output.read_text(encoding="utf-8")
    assert md.startswith("| nome | cep | itens | idade |")
    assert "| João | 01234-000 | \\[1, 2\\] |  |" in md


def test_empty_spreadsheet_to_table_explains(tmp_path):
    from openpyxl import Workbook

    src = tmp_path / "vazia.xlsx"
    Workbook().save(src)
    with pytest.raises(ConversionError, match="não tem dados"):
        convert_file(src, "html", out_dir=tmp_path / "o")
