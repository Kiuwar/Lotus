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
    _run(src, dst, ["-vn", *AUDIO_CODEC[dst.suffix.lstrip(".")]])


@register(VIDEO, VIDEO, category="Vídeo", notes=NOTES, available=has_ffmpeg)
def to_video(src: Path, dst: Path, options: dict) -> None:
    _run(src, dst, VIDEO_CODEC[dst.suffix.lstrip(".")])
