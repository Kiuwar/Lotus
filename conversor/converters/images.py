"""Conversões de imagem com Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFile, ImageOps

from conversor.core.registry import register

IMAGES = ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico"]

PIL_FORMAT = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "gif": "GIF",
    "tiff": "TIFF",
    "ico": "ICO",
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


@register(IMAGES, IMAGES, category="Imagem")
def convert_image(src: Path, dst: Path, options: dict) -> None:
    target = dst.suffix.lstrip(".")
    im = _open(src, options)
    out = _prepare(im, target, src.name, options)
    kwargs: dict = {}
    if target in ("jpg", "webp"):
        kwargs["quality"] = int(options.get("quality", 90))
    if target == "ico":
        # Tamanhos padrão de ícone do Windows; o Pillow ignora os maiores que a imagem.
        kwargs["sizes"] = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    out.save(dst, format=PIL_FORMAT[target], **kwargs)


@register(IMAGES, ["pdf"], category="Imagem", notes="Uma página por imagem.")
def image_to_pdf(src: Path, dst: Path, options: dict) -> None:
    out = _prepare(_open(src, options), "pdf", src.name, options)
    out.save(dst, format="PDF", resolution=float(options.get("dpi", 150)))
