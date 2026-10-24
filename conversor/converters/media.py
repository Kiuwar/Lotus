"""Conversões de áudio e vídeo via ffmpeg (programa externo, opcional).

O ffmpeg NÃO é embutido no aplicativo (licença e tamanho). Ele é procurado em:
1. variável de ambiente CONVERSOR_FFMPEG (caminho do ffmpeg.exe);
2. pasta "ffmpeg" ao lado do executável do aplicativo;
3. PATH do sistema.
Sem ffmpeg, essas conversões aparecem como indisponíveis em vez de falhar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from conversor.core.registry import register
from conversor.core.validate import _no_window

AUDIO = ["mp3", "wav", "ogg", "flac", "m4a"]
VIDEO = ["mp4", "mkv", "webm", "avi", "mov"]

# Codecs explícitos: o padrão do ffmpeg muda conforme a compilação instalada,
# então não dependemos dele.
AUDIO_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
}
VIDEO_CODEC = {
    "mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "mov": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "mkv": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "webm": ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-c:a", "libopus"],
    "avi": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame", "-q:a", "2"],
}

NOTES = "Requer ffmpeg instalado (veja README, seção ffmpeg)."


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    env = os.environ.get("CONVERSOR_FFMPEG")
    if env and Path(env).is_file():
        return env
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    for name in ("ffmpeg.exe", "ffmpeg"):
        local = app_dir / "ffmpeg" / name
        if local.is_file():
            return str(local)
    return shutil.which("ffmpeg")


def has_ffmpeg() -> bool:
    return ffmpeg_path() is not None


@lru_cache(maxsize=4)
def _codificadores(exe: str) -> frozenset[str]:
    """Nomes da lista `ffmpeg -encoders` (2ª coluna) da compilação instalada."""
    proc = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True,
                          errors="replace", **_no_window())
    nomes = set()
    for linha in proc.stdout.splitlines():
        partes = linha.split()
        if len(partes) >= 2 and len(partes[0]) == 6 and partes[0] != "------":
            nomes.add(partes[1])
    return frozenset(nomes)


def tem_codificador(nome: str) -> bool:
    exe = ffmpeg_path()
    return bool(exe) and nome in _codificadores(exe)


# O ffmpeg do Homebrew (Mac) deixou de trazer o libvorbis. O codificador
# Vorbis interno do ffmpeg existe em toda compilação, mas é experimental
# (exige -strict -2) e só aceita 2 canais — conferido rodando o ffmpeg.
OGG_INTERNO = ["-c:a", "vorbis", "-strict", "-2", "-ac", "2", "-q:a", "5"]
AVISO_OGG_INTERNO = (
    "Este ffmpeg não tem o codificador libvorbis; o OGG foi gerado com o codificador "
    "Vorbis interno (experimental, qualidade um pouco menor) e em estéreo — áudio com "
    "mais de 2 canais foi mixado para 2. Para a melhor qualidade, instale um ffmpeg "
    "com libvorbis (no Mac: brew install ffmpeg-full)."
)


def _run(src: Path, dst: Path, args: list[str]) -> None:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError(NOTES)
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(src), *args, str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", **_no_window())
    if proc.returncode != 0:
        msg = proc.stderr.strip().splitlines()
        raise RuntimeError("ffmpeg: " + (msg[-1] if msg else f"código {proc.returncode}"))


@register(AUDIO + VIDEO, AUDIO, category="Áudio", notes=NOTES, available=has_ffmpeg)
def to_audio(src: Path, dst: Path, options: dict) -> None:
    alvo = dst.suffix.lstrip(".")
    codec = AUDIO_CODEC[alvo]
    if alvo == "ogg" and not tem_codificador("libvorbis"):
        codec = OGG_INTERNO
        options.setdefault("_warnings", []).append(AVISO_OGG_INTERNO)
    _run(src, dst, ["-vn", *codec])


@register(VIDEO, VIDEO, category="Vídeo", notes=NOTES, available=has_ffmpeg)
def to_video(src: Path, dst: Path, options: dict) -> None:
    _run(src, dst, VIDEO_CODEC[dst.suffix.lstrip(".")])
