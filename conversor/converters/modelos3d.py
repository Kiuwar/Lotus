"""Modelos 3D para impressão: STL, OBJ, 3MF, PLY, OFF e GLB entre si e uma
prévia em imagem (PNG/JPG) do modelo.

Malhas lidas e gravadas pelo trimesh (MIT; 3MF com lxml em modo seguro:
sem entidades externas e sem rede). Unidade de trabalho: MILÍMETROS, o padrão
dos fatiadores (Cura, PrusaSlicer, Bambu/Orca):
- STL, OBJ, PLY e OFF não guardam unidade: considerados em mm;
- 3MF guarda: convertido para mm quando for outra;
- GLB (glTF) é em METROS pela especificação: ×1000 ao virar mm (e o contrário).
Perdas avisadas (regra 7): cores/texturas, várias peças unidas numa malha,
malha aberta (o fatiador pode precisar reparar).
"""

from __future__ import annotations

import math
from pathlib import Path

from conversor.core.engine import ConversionError
from conversor.core.registry import register

MALHAS = ["stl", "obj", "3mf", "ply", "off", "glb"]
COM_COR = {"3mf", "ply", "glb", "obj"}  # formatos que guardam cor
NOTA = "Medidas em milímetros (GLB em metros, convertido); cores e texturas podem se perder."
NOTA_PREVIA = "Imagem do modelo em perspectiva isométrica (prévia para catálogo/mensagens)."


def _avisar(options: dict, texto: str) -> None:
    avisos = options.setdefault("_warnings", [])
    if texto not in avisos:
        avisos.append(texto)


def _fator_para_mm(unidade: str | None) -> float:
    u = (unidade or "").lower().rstrip("s")
    return {"millimeter": 1.0, "mm": 1.0, "centimeter": 10.0, "cm": 10.0, "meter": 1000.0,
            "m": 1000.0, "inch": 25.4, "in": 25.4, "foot": 304.8, "micron": 0.001,
            "micrometer": 0.001}.get(u, 1.0)


def ler_malha(src: Path, fmt: str, options: dict):
    """Malha única (trimesh.Trimesh) em milímetros."""
    import trimesh

    try:
        obj = trimesh.load(str(src), file_type=fmt, allow_remote=False)
    except Exception as e:  # noqa: BLE001 - arquivo corrompido ou de outro tipo
        raise ConversionError(f"{src.name} não pôde ser lido como {fmt.upper()} ({e}).") from e
    unidade = getattr(obj, "units", None)
    if isinstance(obj, trimesh.Scene):
        pecas = [g for g in obj.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not pecas:
            raise ConversionError(f"{src.name} não tem nenhuma malha 3D (só pontos, linhas ou vazio).")
        if len(pecas) > 1:
            _avisar(options, f"{src.name} tem {len(pecas)} peças; foram unidas num só modelo, "
                             "nas posições originais.")
        malha = obj.to_mesh()
    elif isinstance(obj, trimesh.Trimesh):
        malha = obj
    else:
        raise ConversionError(f"{src.name} não tem uma malha 3D (talvez só pontos ou linhas).")
    if len(malha.faces) == 0:
        raise ConversionError(f"{src.name} não tem triângulos.")
    if fmt == "glb":
        fator = 1000.0
        _avisar(options, "GLB usa metros (padrão glTF); as medidas foram convertidas para milímetros.")
    elif fmt == "3mf":
        fator = _fator_para_mm(unidade)
        if fator != 1.0:
            _avisar(options, f"{src.name} estava em {unidade}; convertido para milímetros.")
    else:
        fator = 1.0
    if fator != 1.0:
        malha.apply_scale(fator)
    malha.units = "millimeters"
    return malha


def gravar_malha(malha, dst: Path, alvo: str, options: dict, origem: str = "") -> None:
    if origem in COM_COR and alvo not in COM_COR and getattr(malha.visual, "kind", None):
        _avisar(options, f"{alvo.upper()} não guarda cores: o modelo ficou sem cor.")
    if not malha.is_watertight:
        _avisar(options, "A malha não é fechada (tem buracos ou faces soltas); o fatiador pode "
                         "precisar repará-la.")
    if alvo == "glb":
        malha = malha.copy()
        malha.apply_scale(0.001)  # glTF é em metros
    if alvo == "obj":
        dados = malha.export(file_type="obj", include_texture=False, header="Lotus")
    else:
        dados = malha.export(file_type=alvo)
    Path(dst).write_bytes(dados if isinstance(dados, bytes) else dados.encode("utf-8"))


@register(MALHAS, MALHAS, category="3D", notes=NOTA)
def converter_malha(src: Path, dst: Path, options: dict) -> None:
    origem = options.get("_source_format") or src.suffix.lstrip(".").lower()
    malha = ler_malha(src, origem, options)
    gravar_malha(malha, dst, dst.suffix.lstrip(".").lower(), options, origem)


# ---------- prévia (imagem do modelo) ----------

COR_MODELO = (58, 134, 255)  # azul; o fundo é branco


def desenhar_previa(malha, lado: int = 1024, cor: tuple = COR_MODELO):
    """Desenho isométrico (frente-direita, de cima), sombreado pela direção de
    cada face e pintado do fundo para a frente. Só numpy + Pillow."""
    import numpy as np
    from PIL import Image, ImageDraw

    ss = 2  # supersampling: desenha em 2× e reduz (bordas lisas)
    tam = lado * ss
    frente = -np.array([1.0, -1.0, 1.0]) / math.sqrt(3)       # olhando para a origem
    direita = np.cross(frente, [0.0, 0.0, 1.0])
    direita /= np.linalg.norm(direita)
    cima = np.cross(direita, frente)
    v = malha.vertices - malha.bounds.mean(axis=0)
    x, y, prof = v @ direita, v @ cima, v @ frente
    extensao = max(x.max() - x.min(), y.max() - y.min()) or 1.0
    escala = tam * 0.84 / extensao
    px = (x - (x.max() + x.min()) / 2) * escala + tam / 2
    py = tam / 2 - (y - (y.max() + y.min()) / 2) * escala
    faces = malha.faces
    normais = malha.face_normals
    visiveis = (normais @ -frente) > 0  # só as faces voltadas para quem olha
    faces, normais = faces[visiveis], normais[visiveis]
    luz = np.array([0.35, -0.55, 1.0]) / np.linalg.norm([0.35, -0.55, 1.0])
    brilho = 0.38 + 0.62 * np.clip(normais @ luz, 0, 1)
    ordem = np.argsort(-prof[faces].mean(axis=1))  # do mais longe para o mais perto
    img = Image.new("RGB", (tam, tam), (255, 255, 255))
    d = ImageDraw.Draw(img)
    cor_arr = np.array(cor, dtype=float)
    for i in ordem:
        f = faces[i]
        c = tuple(int(round(v_)) for v_ in np.minimum(255, cor_arr * brilho[i] + 30 * brilho[i]))
        d.polygon([(px[f[0]], py[f[0]]), (px[f[1]], py[f[1]]), (px[f[2]], py[f[2]])], fill=c)
    return img.resize((lado, lado), Image.LANCZOS)


@register(MALHAS, ["png", "jpg"], category="3D", notes=NOTA_PREVIA)
def previa_malha(src: Path, dst: Path, options: dict) -> None:
    origem = options.get("_source_format") or src.suffix.lstrip(".").lower()
    malha = ler_malha(src, origem, options)
    lado = int(options.get("lado_previa", 1024))
    img = desenhar_previa(malha, lado)
    alvo = dst.suffix.lstrip(".").lower()
    if alvo == "jpg":
        img.save(dst, format="JPEG", quality=int(options.get("quality", 90)))
    else:
        img.save(dst, format="PNG")
