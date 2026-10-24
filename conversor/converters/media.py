"""Conversões de áudio e vídeo via ffmpeg (programa externo, opcional).

O ffmpeg NÃO é embutido no aplicativo (licença e tamanho). Ele é procurado em:
1. variável de ambiente CONVERSOR_FFMPEG (caminho do ffmpeg.exe);
2. pasta "ffmpeg" ao lado do executável do aplicativo;
3. PATH do sistema.
Sem ffmpeg, essas conversões aparecem como indisponíveis em vez de falhar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from conversor.core.registry import register
from conversor.core.validate import _no_window

AUDIO = ["mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma", "aiff"]
VIDEO = ["mp4", "mkv", "webm", "avi", "mov", "wmv", "mpeg", "m4v"]

# Codecs explícitos: o padrão do ffmpeg muda conforme a compilação instalada,
# então não dependemos dele.
AUDIO_CODEC = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "aac": ["-c:a", "aac", "-b:a", "192k"],          # .aac = fluxo ADTS
    "opus": ["-c:a", "libopus", "-b:a", "128k"],     # .opus = Opus em Ogg
    "wma": ["-c:a", "wmav2", "-b:a", "192k"],        # .wma = ASF
    "aiff": ["-c:a", "pcm_s16be"],                   # sem perda, como o WAV
}
VIDEO_CODEC = {
    "mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "mov": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "mkv": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "webm": ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-c:a", "libopus"],
    "avi": ["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame", "-q:a", "2"],
    "m4v": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
    "wmv": ["-c:v", "wmv2", "-b:v", "2M", "-c:a", "wmav2", "-b:a", "192k"],
    "mpeg": ["-c:v", "mpeg2video", "-q:v", "4", "-c:a", "mp2", "-b:a", "192k"],
}
# Taxas de quadros que o MPEG-2 aceita (padrão do formato).
FPS_MPEG2 = [(24000, 1001), (24, 1), (25, 1), (30000, 1001), (30, 1), (50, 1), (60000, 1001), (60, 1)]

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


# Opus sem libopus: o codificador Opus interno do ffmpeg (experimental) só
# trabalha a 48 kHz; em 2 canais por segurança. Conferido rodando o ffmpeg.
OPUS_INTERNO = ["-c:a", "opus", "-strict", "-2", "-ar", "48000", "-ac", "2", "-b:a", "128k"]
AVISO_OPUS_INTERNO = (
    "Este ffmpeg não tem o codificador libopus; o OPUS foi gerado com o codificador interno "
    "(experimental) em estéreo a 48 kHz. Para a melhor qualidade, instale um ffmpeg com libopus."
)
GIF_SEGUNDOS, GIF_FPS, GIF_LARGURA = 15, 10, 480


def _aviso(options: dict, texto: str) -> None:
    options.setdefault("_warnings", []).append(texto)


def ffprobe_path() -> str | None:
    """ffprobe ao lado do ffmpeg escolhido; senão, o do PATH."""
    exe = ffmpeg_path()
    if exe:
        vizinho = Path(exe).with_name("ffprobe.exe" if exe.lower().endswith(".exe") else "ffprobe")
        if vizinho.is_file():
            return str(vizinho)
    return shutil.which("ffprobe")


def sondar(src: Path) -> dict:
    """Duração, quadros/s e faixas do arquivo (valores None se não der para saber)."""
    info = {"duracao": None, "fps": None, "tem_video": None, "tem_audio": None}
    probe = ffprobe_path()
    if not probe:
        return info
    proc = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,r_frame_rate",
         "-of", "json", str(src)], capture_output=True, text=True, errors="replace", **_no_window())
    try:
        dados = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return info
    streams = dados.get("streams", [])
    info["tem_video"] = any(st.get("codec_type") == "video" for st in streams)
    info["tem_audio"] = any(st.get("codec_type") == "audio" for st in streams)
    try:
        info["duracao"] = float(dados.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass
    for st in streams:
        if st.get("codec_type") == "video" and "/" in str(st.get("r_frame_rate", "")):
            num, den = st["r_frame_rate"].split("/")
            if float(den):
                info["fps"] = float(num) / float(den)
            break
    return info


def fps_mpeg2(fps: float | None) -> tuple[str | None, str | None]:
    """(-r para o MPEG-2, aviso). Taxa já padrão: nada muda. Outra: a menor
    taxa padrão acima dela (quadros repetidos, nada se perde); acima de 60,
    60 quadros/s com aviso (quadros descartados)."""
    if not fps:
        return None, None
    padroes = [n / d for n, d in FPS_MPEG2]
    if any(abs(fps - p) < 0.01 for p in padroes):
        return None, None
    for (n, d), p in zip(FPS_MPEG2, padroes):
        if p >= fps:
            return (f"{n}/{d}" if d != 1 else str(n)), None
    return "60", (f"O MPEG-2 aceita no máximo 60 quadros/s; o vídeo tinha {fps:.0f} e "
                  "quadros foram descartados.")


def _executar(argumentos: list[str]) -> None:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError(NOTES)
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", *argumentos]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", **_no_window())
    if proc.returncode != 0:
        msg = proc.stderr.strip().splitlines()
        raise RuntimeError("ffmpeg: " + (msg[-1] if msg else f"código {proc.returncode}"))


def _run(src: Path, dst: Path, args: list[str]) -> None:
    _executar(["-i", str(src), *args, str(dst)])


@register(AUDIO + VIDEO, AUDIO, category="Áudio", notes=NOTES, available=has_ffmpeg)
def to_audio(src: Path, dst: Path, options: dict) -> None:
    alvo = dst.suffix.lstrip(".")
    codec = AUDIO_CODEC[alvo]
    if alvo == "ogg" and not tem_codificador("libvorbis"):
        codec = OGG_INTERNO
        _aviso(options, AVISO_OGG_INTERNO)
    elif alvo == "opus" and not tem_codificador("libopus"):
        codec = OPUS_INTERNO
        _aviso(options, AVISO_OPUS_INTERNO)
    if sondar(src)["tem_audio"] is False:
        raise RuntimeError(f"{src.name} não tem faixa de áudio para extrair.")
    _run(src, dst, ["-vn", *codec])


@register(VIDEO, VIDEO, category="Vídeo", notes=NOTES, available=has_ffmpeg)
def to_video(src: Path, dst: Path, options: dict) -> None:
    alvo = dst.suffix.lstrip(".")
    args = list(VIDEO_CODEC[alvo])
    if alvo == "mpeg":
        taxa, aviso = fps_mpeg2(sondar(src)["fps"])
        if taxa:
            args += ["-r", taxa]
        if aviso:
            _aviso(options, aviso)
    _run(src, dst, args)


@register(VIDEO, ["gif"], category="Vídeo", notes=NOTES, available=has_ffmpeg)
def video_para_gif(src: Path, dst: Path, options: dict) -> None:
    """GIF animado com paleta própria (cores melhores que a paleta padrão)."""
    info = sondar(src)
    filtro = (f"fps={GIF_FPS},scale='min({GIF_LARGURA},iw)':-2:flags=lanczos,"
              "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
    texto = f"GIF não tem som; foi gerado com {GIF_FPS} quadros/s e até {GIF_LARGURA} px de largura"
    if info["duracao"] is None or info["duracao"] > GIF_SEGUNDOS:
        texto += f" e só com os primeiros {GIF_SEGUNDOS} s do vídeo"
    _aviso(options, texto + ".")
    _run(src, dst, ["-t", str(GIF_SEGUNDOS), "-vf", filtro, "-loop", "0"])


@register(VIDEO, ["png", "jpg"], category="Vídeo", notes=NOTES, available=has_ffmpeg)
def quadro_do_video(src: Path, dst: Path, options: dict) -> None:
    """Uma imagem do vídeo (miniatura): em 1 s, ou em 10% de vídeos curtos."""
    dur = sondar(src)["duracao"]
    t = min(1.0, dur * 0.1) if dur else 0.0
    qualidade = ["-q:v", "2"] if dst.suffix == ".jpg" else []
    _aviso(options, f"Foi salva uma única imagem do vídeo (o quadro em {t:.1f} s).")
    _executar(["-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", *qualidade, str(dst)])


@register(AUDIO, ["mp4"], category="Vídeo", notes=NOTES, available=has_ffmpeg)
def audio_para_mp4(src: Path, dst: Path, options: dict) -> None:
    """MP4 com tela preta e o áudio (para enviar a sites que só aceitam vídeo)."""
    _aviso(options, "O MP4 mostra uma tela preta enquanto o áudio toca.")
    _executar(["-f", "lavfi", "-i", "color=c=black:s=1280x720:r=2", "-i", str(src), "-shortest",
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-tune", "stillimage",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(dst)])
