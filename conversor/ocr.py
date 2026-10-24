"""OCR (texto de imagem) com o reconhecedor que JÁ VEM no sistema, offline.

- Windows 10/11: Windows.Media.Ocr, pelos pacotes `winrt-*` 3.2.1 (MIT).
  API conferida nos arquivos de tipos da versão fixada:
  OcrEngine.try_create_from_language / try_create_from_user_profile_languages,
  OcrEngine.max_image_dimension, engine.recognize_async(SoftwareBitmap) →
  OcrResult.lines[].text; SoftwareBitmap.create_copy_from_buffer(bytes,
  BitmapPixelFormat.BGRA8, largura, altura). Usa os idiomas instalados no
  Windows; sem português, usa o idioma do perfil e avisa.
- Mac: framework Vision (pyobjc-framework-Vision 12.2.2, MIT):
  VNRecognizeTextRequest + VNImageRequestHandler. Os idiomas suportados são
  consultados no próprio Mac (não supomos a versão do macOS).
- Outros sistemas: indisponível (a conversão explica).

Sem rede (regra 8): os dois reconhecedores rodam no computador.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from conversor.logs import get_logger

IDIOMA = "pt-BR"
NOMES_VISION = ["VNRecognizeTextRequest", "VNImageRequestHandler",
                "VNRequestTextRecognitionLevelAccurate"]


class OcrIndisponivel(Exception):
    pass


def motivo() -> str:
    if sys.platform == "win32":
        return ("o reconhecimento de texto do Windows não está disponível. Como resolver: em "
                "Configurações → Hora e idioma → Idioma, instale o Português (Brasil) com o "
                "recurso de reconhecimento de texto")
    if sys.platform == "darwin":
        return "o reconhecimento de texto do macOS (Vision) não está disponível nesta versão do Mac"
    return "o OCR do Lotus existe só no Windows 10/11 e no Mac"


# ---------- Windows ----------

class _Windows:
    def __init__(self):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        self.OcrEngine = OcrEngine
        self.aviso = None
        motor = OcrEngine.try_create_from_language(Language(IDIOMA))
        if motor is None:
            motor = OcrEngine.try_create_from_user_profile_languages()
            if motor is not None:
                self.aviso = (f"O reconhecimento em português não está instalado no Windows; foi usado "
                              f"\"{motor.recognizer_language.language_tag}\" e acentos podem sair errados. "
                              "Como resolver: Configurações → Hora e idioma → Idioma → adicione "
                              "Português (Brasil).")
        if motor is None:
            raise OcrIndisponivel(motivo())
        self.motor = motor

    def reconhecer(self, imagem) -> str:
        import asyncio

        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap

        imagem = _caber(imagem, int(self.OcrEngine.max_image_dimension))
        rgba = imagem.convert("RGBA")
        bitmap = SoftwareBitmap.create_copy_from_buffer(rgba.tobytes("raw", "BGRA"),
                                                        BitmapPixelFormat.BGRA8, rgba.width, rgba.height)

        async def _rodar():
            return await self.motor.recognize_async(bitmap)

        resultado = asyncio.run(_rodar())
        return "\n".join(linha.text for linha in resultado.lines)


# ---------- Mac ----------

class _Mac:
    def __init__(self):
        import Vision

        self.V = Vision
        self.aviso = None
        self.idiomas = None
        suportados = self._suportados()
        if suportados is not None:
            pt = [i for i in suportados if str(i).lower().startswith("pt")]
            if pt:
                self.idiomas = [str(pt[0])]
            else:
                self.aviso = ("Esta versão do macOS não reconhece texto em português; foi usado o "
                              "inglês e acentos podem sair errados. Como resolver: atualize o macOS.")

    def _suportados(self):
        V = self.V
        req = V.VNRecognizeTextRequest.alloc().init()
        try:  # macOS 12+
            r = req.supportedRecognitionLanguagesAndReturnError_(None)
            return list(r[0] if isinstance(r, tuple) else r)
        except Exception:  # noqa: BLE001 - método mais antigo (macOS 10.15/11)
            pass
        try:
            r = V.VNRecognizeTextRequest.supportedRecognitionLanguagesForTextRecognitionLevel_revision_error_(
                V.VNRequestTextRecognitionLevelAccurate, req.revision(), None)
            return list(r[0] if isinstance(r, tuple) else r)
        except Exception:  # noqa: BLE001
            get_logger().exception("idiomas do Vision")
            return None

    def reconhecer(self, imagem) -> str:
        import io

        from Foundation import NSData

        V = self.V
        png = io.BytesIO()
        imagem.convert("RGB").save(png, format="PNG")
        dados = NSData.dataWithBytes_length_(png.getvalue(), len(png.getvalue()))
        req = V.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(V.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(True)
        if self.idiomas:
            req.setRecognitionLanguages_(self.idiomas)
        handler = V.VNImageRequestHandler.alloc().initWithData_options_(dados, {})
        ok = handler.performRequests_error_([req], None)
        if isinstance(ok, tuple):
            ok, erro = ok
            if not ok:
                raise RuntimeError(f"Vision: {erro}")
        linhas = []
        for obs in req.results() or []:
            cand = obs.topCandidates_(1)
            if cand:
                caixa = obs.boundingBox()  # origem embaixo à esquerda, de 0 a 1
                linhas.append((-round(caixa.origin.y + caixa.size.height, 3), caixa.origin.x,
                               str(cand[0].string())))
        return "\n".join(t for _, _, t in sorted(linhas))


# ---------- comum ----------

def _caber(imagem, maximo: int):
    if maximo and max(imagem.size) > maximo:
        fator = maximo / max(imagem.size)
        imagem = imagem.resize((max(1, int(imagem.width * fator)), max(1, int(imagem.height * fator))))
    return imagem


@lru_cache(maxsize=1)
def _backend():
    if sys.platform == "win32":
        return _Windows()
    if sys.platform == "darwin":
        return _Mac()
    raise OcrIndisponivel(motivo())


def disponivel() -> bool:
    try:
        _backend()
        return True
    except Exception:  # noqa: BLE001
        get_logger().info("OCR indisponível", exc_info=True)
        return False


def reconhecer(imagem) -> tuple[str, str | None]:
    """(texto, aviso de idioma ou None). Levanta OcrIndisponivel."""
    try:
        b = _backend()
    except OcrIndisponivel:
        raise
    except Exception as e:  # noqa: BLE001 - pacote ausente, API recusada…
        get_logger().exception("OCR")
        raise OcrIndisponivel(motivo()) from e
    return b.reconhecer(imagem), b.aviso
