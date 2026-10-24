"""Conversões de imagem com Pillow.

AVIF: leitor e gravador do próprio Pillow (só se a build tiver libavif;
`features.check("avif")`). HEIC/HEIF (fotos do iPhone): só LEITURA, pelo
pi-heif (libheif + libde265, LGPL, sem codificador HEVC). Gravar HEIC exigiria
o x265 (GPL) e não é oferecido.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFile, ImageOps, features

from conversor.core.registry import register
from conversor.logs import get_logger

IMAGES = ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico"]

PIL_FORMAT = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "gif": "GIF",
    "tiff": "TIFF",
    "ico": "ICO",
    "avif": "AVIF",
}

# Formatos sem canal de transparência: o fundo transparente vira branco.
NO_ALPHA = {"jpg", "bmp"}


def _flatten_on_white(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.getchannel("A"))
    return bg


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def _open(src: Path, options: dict) -> Image.Image:
    """Abre a imagem; se estiver truncada (download incompleto), tenta recuperar."""
    try:
        return _load(src, options)
    except OSError as e:
        if "truncated" not in str(e).lower():
            raise
    # Reparo: o Pillow consegue ler a parte íntegra de uma imagem truncada.
    # A flag é global no Pillow, então é restaurada logo em seguida.
    previous = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        im = _load(src, options)
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = previous
    options.setdefault("_warnings", []).append(
        f"{src.name} está danificado (incompleto); a parte recuperável foi convertida."
    )
    return im


def _load(src: Path, options: dict) -> Image.Image:
    """Carrega o primeiro quadro na memória e fecha o arquivo de origem."""
    with Image.open(src) as raw:
        frames = getattr(raw, "n_frames", 1)
        if frames > 1:
            options.setdefault("_warnings", []).append(
                f"{src.name} tem {frames} quadros/páginas; apenas o primeiro foi convertido."
            )
        raw.seek(0)
        # Corrige rotação de fotos de celular (tag EXIF Orientation); devolve cópia.
        im = ImageOps.exif_transpose(raw)
        im.load()
    return im


def _prepare(im: Image.Image, target: str, src_name: str, options: dict) -> Image.Image:
    if target in NO_ALPHA or target == "pdf":
        if _has_alpha(im):
            options.setdefault("_warnings", []).append(
                f"{src_name}: transparência substituída por fundo branco ({target.upper()} não tem transparência)."
            )
            return _flatten_on_white(im)
        return im.convert("RGB") if im.mode not in ("RGB", "L") else im
    if target == "ico":
        return im.convert("RGBA")
    if im.mode in ("I;16", "I", "F"):  # imagens de 16/32 bits (ex.: TIFF científico)
        return im.convert("I").point(lambda v: v / 256).convert("L")
    if im.mode == "CMYK" and target in {"png", "gif", "webp", "ico"}:
        return im.convert("RGB")
    return im


@lru_cache(maxsize=1)
def avif_disponivel() -> bool:
    return bool(features.check("avif"))


@lru_cache(maxsize=1)
def heic_disponivel() -> bool:
    try:
        import pi_heif

        pi_heif.register_heif_opener()
    except Exception:  # noqa: BLE001 - sem o pi-heif só o HEIC fica indisponível
        get_logger().exception("pi-heif indisponível")
        return False
    return True


def _heic_pronto() -> None:
    # O leitor HEIF é registrado no Pillow sob demanda (na 1ª conversão).
    if not heic_disponivel():
        raise RuntimeError("leitor de HEIC indisponível nesta instalação. "
                           "Como resolver: reinstale o Lotus pelo instalador oficial")


AVIF_NOTA = "Requer Pillow com suporte a AVIF (incluído no instalador)."
HEIC_NOTA = "HEIC/HEIF só como origem (fotos do iPhone); gravar HEIC não é oferecido."


@register(IMAGES, IMAGES, category="Imagem")
def convert_image(src: Path, dst: Path, options: dict) -> None:
    target = dst.suffix.lstrip(".")
    im = _open(src, options)
    out = _prepare(im, target, src.name, options)
    kwargs: dict = {}
    if target in ("jpg", "webp", "avif"):
        kwargs["quality"] = int(options.get("quality", 90))
    if target == "ico":
        # Tamanhos padrão de ícone do Windows; o Pillow ignora os maiores que a imagem.
        kwargs["sizes"] = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    out.save(dst, format=PIL_FORMAT[target], **kwargs)


@register(IMAGES, ["pdf"], category="Imagem", notes="Uma página por imagem.")
def image_to_pdf(src: Path, dst: Path, options: dict) -> None:
    out = _prepare(_open(src, options), "pdf", src.name, options)
    out.save(dst, format="PDF", resolution=float(options.get("dpi", 150)))


def _foto_para_qualquer(src: Path, dst: Path, options: dict) -> None:
    """Origem AVIF/HEIC: o mesmo caminho das outras imagens (inclusive PDF)."""
    if dst.suffix == ".pdf":
        image_to_pdf(src, dst, options)
    else:
        convert_image(src, dst, options)


# AVIF: entra e sai (o Pillow lê e grava).
register(["avif"], IMAGES + ["pdf"], category="Imagem", notes=AVIF_NOTA,
         available=avif_disponivel)(_foto_para_qualquer)
register(IMAGES, ["avif"], category="Imagem", notes=AVIF_NOTA, available=avif_disponivel)(convert_image)


@register(["heic"], IMAGES + ["pdf"], category="Imagem", notes=HEIC_NOTA, available=heic_disponivel)
def heic_para_imagem(src: Path, dst: Path, options: dict) -> None:
    _heic_pronto()
    _foto_para_qualquer(src, dst, options)


register(["heic"], ["avif"], category="Imagem", notes=HEIC_NOTA,
         available=lambda: heic_disponivel() and avif_disponivel())(heic_para_imagem)
