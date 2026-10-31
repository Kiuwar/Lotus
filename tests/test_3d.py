"""Impressão 3D: o CONTEÚDO tem de sair certo (medidas em mm, volume, furos,
espessuras), não basta o arquivo existir."""

from __future__ import annotations

import zipfile

import pytest
from PIL import Image

from conversor.core.detect import DetectionError, detect
from conversor.core.engine import ConversionError, convert_file

from .conftest import make_malha

trimesh = pytest.importorskip("trimesh")
MALHAS = ["stl", "obj", "3mf", "ply", "off", "glb"]


def _abrir(caminho, fmt):
    m = trimesh.load(str(caminho), file_type=fmt, force="mesh")
    return m.copy().apply_scale(1000) if fmt == "glb" else m  # GLB é em metros


@pytest.mark.parametrize("origem", MALHAS)
@pytest.mark.parametrize("alvo", MALHAS)
def test_mesh_conversions_keep_size_and_volume_in_mm(tmp_path, sample, origem, alvo):
    if origem == alvo:
        pytest.skip("mesmo formato")
    r = convert_file(sample(origem), alvo, out_dir=tmp_path / "o")
    m = _abrir(r.output, alvo)
    assert sorted(round(x, 3) for x in m.extents) == [10.0, 20.0, 30.0]
    assert m.volume == pytest.approx(6000, rel=1e-4)
    assert m.is_watertight


def test_glb_is_converted_from_meters_with_warning(tmp_path, sample):
    r = convert_file(sample("glb"), "stl", out_dir=tmp_path / "o")
    assert any("metros" in w for w in r.warnings)
    assert sorted(_abrir(r.output, "stl").extents.round(3)) == [10, 20, 30]


def test_3mf_in_inches_becomes_millimeters(tmp_path):
    src = make_malha(tmp_path / "pol.3mf", "3mf", extents=(1.0, 2.0, 3.0))
    with zipfile.ZipFile(src) as z:
        partes = {n: z.read(n) for n in z.namelist()}
    partes["3D/3dmodel.model"] = partes["3D/3dmodel.model"].replace(b'unit="millimeter"', b'unit="inch"')
    with zipfile.ZipFile(src, "w") as z:
        for n, d in partes.items():
            z.writestr(n, d)
    r = convert_file(src, "stl", out_dir=tmp_path / "o")
    assert sorted(_abrir(r.output, "stl").extents.round(2)) == [25.4, 50.8, 76.2]
    assert any("convertido para milímetros" in w for w in r.warnings)


def test_several_parts_are_joined_with_warning(tmp_path):
    cena = trimesh.Scene([trimesh.creation.box((5, 5, 5)),
                          trimesh.creation.box((5, 5, 5)).apply_translation((20, 0, 0))])
    src = tmp_path / "duas.3mf"
    src.write_bytes(cena.export(file_type="3mf"))
    r = convert_file(src, "stl", out_dir=tmp_path / "o")
    assert any("2 peças" in w for w in r.warnings)
    assert _abrir(r.output, "stl").volume == pytest.approx(250)


@pytest.mark.parametrize("fmt", ["3mf", "glb", "ply", "off"])
def test_3d_formats_detected_by_content(sample, tmp_path, fmt):
    original = sample(fmt)
    renomeado = tmp_path / f"modelo.bin_{fmt}"
    renomeado.write_bytes(original.read_bytes())
    assert detect(renomeado).fmt == fmt, "reconhecido pelo conteúdo, não pela extensão"


def test_stl_detection_binary_ascii_and_fake(tmp_path, sample):
    assert detect(sample("stl")).fmt == "stl"
    ascii_ = tmp_path / "a.stl"
    ascii_.write_bytes(trimesh.creation.box((1, 1, 1)).export(file_type="stl_ascii").encode())
    assert detect(ascii_).fmt == "stl"
    falso = tmp_path / "falso.stl"
    falso.write_bytes(b"isto nao e um modelo 3d" * 10)
    with pytest.raises(DetectionError, match="não é um STL"):
        detect(falso)


def test_open_mesh_warns_slicer_may_repair(tmp_path):
    aberta = trimesh.creation.box((5, 5, 5))
    aberta.update_faces([True] * 10 + [False] * 2)  # tira um lado: caixa sem tampa
    src = tmp_path / "aberta.stl"
    src.write_bytes(aberta.export(file_type="stl"))
    r = convert_file(src, "3mf", out_dir=tmp_path / "o")
    assert any("não é fechada" in w for w in r.warnings)


@pytest.mark.parametrize("alvo", ["png", "jpg"])
def test_preview_image_shows_the_model(tmp_path, sample, alvo):
    out = convert_file(sample("stl"), alvo, out_dir=tmp_path / "o").output
    with Image.open(out) as im:
        im = im.convert("RGB")
        assert im.size == (1024, 1024)
        assert min(im.getpixel((3, 3))) > 240, "fundo branco"
        cores = im.resize((64, 64)).getcolors(64 * 64)
        azuis = sum(n for n, (r, g, b) in cores if b > r + 40 and b > g)
        assert azuis > 64 * 64 * 0.08, "o modelo azul ocupa a imagem"
        tons = {round(sum(c) / 30) for n, c in cores if c[2] > c[0] + 40}
        assert len(tons) >= 2, "faces com sombreamento diferente (dá volume)"


# ---------- SVG ----------

def test_svg_extruded_to_stl_has_real_size_and_hole(tmp_path, sample):
    r = convert_file(sample("svg"), "stl", out_dir=tmp_path / "o")
    m = _abrir(r.output, "stl")
    assert m.extents.round(3).tolist() == [10.0, 10.0, 2.0]
    assert m.volume == pytest.approx((100 - 16) * 2, rel=1e-3), "o furo de 4×4 mm continua furo"
    assert m.is_watertight and m.bounds[0].round(6).tolist() == [0, 0, 0], "apoiada na mesa"


def test_svg_thickness_and_width_options(tmp_path, sample):
    opts = {"espessura": 3.0, "largura": 50.0}
    r = convert_file(sample("svg"), "3mf", out_dir=tmp_path / "o", options=opts)
    m = _abrir(r.output, "3mf")
    assert m.extents.round(3).tolist() == [50.0, 50.0, 3.0], "a largura não muda a espessura"


def test_svg_outline_only_is_explained(tmp_path):
    src = tmp_path / "linha.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10">'
                   '<rect x="1" y="1" width="8" height="8" fill="none" stroke="black"/></svg>', encoding="utf-8")
    with pytest.raises(ConversionError, match="não tem áreas preenchidas"):
        convert_file(src, "stl", out_dir=tmp_path / "o")


def test_svg_to_png_draws_shape_hole_and_color(tmp_path, sample):
    out = convert_file(sample("svg"), "png", out_dir=tmp_path / "o").output
    with Image.open(out) as im:
        im = im.convert("RGBA")
        assert im.width >= 1000
        w = im.width
        assert im.getpixel((int(w * 0.5), int(w * 0.95)))[:3] == (0, 0, 0), "moldura preta"
        assert im.getpixel((w // 2, w // 2))[3] == 0, "o furo é transparente"
        r, g, b, _ = im.getpixel((int(w * 0.15), int(w * 0.15)))
        assert r > 200 and g < 60, "círculo vermelho"


def test_svg_to_jpg_flattens_on_white(tmp_path, sample):
    r = convert_file(sample("svg"), "jpg", out_dir=tmp_path / "o")
    assert any("fundo branco" in w for w in r.warnings)


def test_svg_to_pdf_keeps_physical_size(tmp_path, sample):
    from pypdf import PdfReader

    out = convert_file(sample("svg"), "pdf", out_dir=tmp_path / "o").output
    pagina = PdfReader(str(out)).pages[0]
    mm = [float(v) * 25.4 / 72 for v in (pagina.mediabox.width, pagina.mediabox.height)]
    assert [round(x, 1) for x in mm] == [10.0, 10.0]


# ---------- DXF (corte a laser) ----------

def test_svg_to_dxf_in_millimeters(tmp_path, sample):
    import ezdxf

    out = convert_file(sample("svg"), "dxf", out_dir=tmp_path / "o").output
    doc = ezdxf.readfile(str(out))
    assert doc.units == 4, "INSUNITS = milímetros"
    xs = [p[0] for e in doc.modelspace().query("LWPOLYLINE") for p in e.get_points("xy")]
    assert round(min(xs), 3) == 0 and round(max(xs), 3) == 10


def test_dxf_to_svg_keeps_measures_and_reports_skipped(tmp_path, sample):
    import ezdxf
    from defusedxml import ElementTree as ET

    src = sample("dxf")
    doc = ezdxf.readfile(str(src))
    doc.modelspace().add_text("cota")
    doc.saveas(str(src))
    r = convert_file(src, "svg", out_dir=tmp_path / "o")
    raiz = ET.parse(str(r.output)).getroot()
    largura_mm = float(raiz.get("width").rstrip("mm"))
    assert largura_mm == pytest.approx(40 * 1.04, rel=1e-3), "40 mm + margem de 2% de cada lado"
    assert len(raiz.findall(".//{http://www.w3.org/2000/svg}polyline")) == 2
    assert any("TEXT" in w for w in r.warnings)


# ---------- litofania ----------

def _faixas(tmp_path):
    img = Image.new("L", (200, 100), 255)
    img.paste(0, (0, 0, 100, 100))  # metade esquerda preta
    src = tmp_path / "foto.png"
    img.save(src)
    return src


def test_lithophane_dark_is_thick_light_is_thin(tmp_path):
    out = convert_file(_faixas(tmp_path), "stl", out_dir=tmp_path / "o").output
    m = _abrir(out, "stl")
    assert m.is_watertight
    assert m.extents[0] == pytest.approx(100, abs=0.01) and m.extents[1] == pytest.approx(50, abs=0.3)
    import numpy as np

    topo = m.vertices[m.vertices[:, 2] > 0.01]
    esquerda = topo[topo[:, 0] < 40][:, 2]
    direita = topo[topo[:, 0] > 60][:, 2]
    assert np.median(esquerda) == pytest.approx(3.0, abs=0.05), "preto = 3 mm"
    assert np.median(direita) == pytest.approx(0.8, abs=0.05), "branco = 0,8 mm"


def test_relief_mode_inverts(tmp_path):
    out = convert_file(_faixas(tmp_path), "3mf", out_dir=tmp_path / "o",
                       options={"modo": "relevo", "largura": 40.0}).output
    m = _abrir(out, "3mf")
    topo = m.vertices[m.vertices[:, 2] > 0.01]
    assert m.extents[0] == pytest.approx(40, abs=0.01)
    assert topo[topo[:, 0] < 15][:, 2].max() == pytest.approx(0.8, abs=0.05), "preto = baixo"


def test_lithophane_transparency_warning(tmp_path):
    src = tmp_path / "logo.png"
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(src)
    r = convert_file(src, "stl", out_dir=tmp_path / "o")
    assert any("transparentes viraram branco" in w for w in r.warnings)
