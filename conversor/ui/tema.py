"""Aparência do Lotus: temas prontos, cores personalizadas e claro/escuro.

Cores-base: as "cores do sistema" do macOS (azul #007AFF, laranja #FF9500…),
nas variantes clara e escura. O usuário escolhe um tema pronto e pode
sobrescrever destaque, fundo e a cor de cada grupo de formatos.

Gravado em <pasta de config>/aparencia.json. Arquivo inválido não derruba o
app: volta ao padrão e o arquivo ruim é guardado como .corrompido.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from conversor.logs import get_logger

GRUPOS = ("Imagem", "Documento", "Texto e dados", "Áudio", "Vídeo")
TAMANHOS = {"P": 0.8, "M": 1.0, "G": 1.25}
FORMAS = ("radial", "cartao")
MODOS = ("auto", "claro", "escuro")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Paleta:
    """Cores já resolvidas (tema + claro/escuro + personalizações)."""

    fundo: str        # fundo do painel / janela
    superficie: str   # cartões e caixas neutras
    texto: str
    texto_sec: str    # rótulos dos grupos
    destaque: str     # cor de foco/hover
    grupos: dict      # nome do grupo -> cor
    escuro: bool
    efeito: str = ""  # "holo": anel iridescente, vidro e brilho neon (render.py)


# (claro, escuro) para cada tema pronto
_MAC_CLARO = dict(fundo="#F5F5F7", superficie="#FFFFFF", texto="#1D1D1F", texto_sec="#6E6E73",
                  destaque="#007AFF", grupos={"Imagem": "#FF9500", "Documento": "#007AFF",
                                              "Texto e dados": "#34C759", "Áudio": "#AF52DE",
                                              "Vídeo": "#FF2D55"})
_MAC_ESCURO = dict(fundo="#1C1C1E", superficie="#2C2C2E", texto="#F5F5F7", texto_sec="#AEAEB2",
                   destaque="#0A84FF", grupos={"Imagem": "#FF9F0A", "Documento": "#0A84FF",
                                               "Texto e dados": "#30D158", "Áudio": "#BF5AF2",
                                               "Vídeo": "#FF375F"})

# Holográfico: claro = perolado; escuro = vidro azul-noite com neon.
_HOLO_CLARO = dict(fundo="#F3F4FB", superficie="#FFFFFF", texto="#15172B", texto_sec="#585C78",
                   destaque="#6C4DFF", efeito="holo",
                   grupos={"Imagem": "#E0409F", "Documento": "#0091D5", "Texto e dados": "#13A884",
                           "Áudio": "#7B57F5", "Vídeo": "#E07B12"})
_HOLO_ESCURO = dict(fundo="#0A0E1F", superficie="#141A33", texto="#EEF1FF", texto_sec="#A9B0D6",
                    destaque="#00E5FF", efeito="holo",
                    grupos={"Imagem": "#FF6AD5", "Documento": "#00D1FF", "Texto e dados": "#5CFFC1",
                            "Áudio": "#B18CFF", "Vídeo": "#FFB46B"})

PRESETS: dict[str, tuple[dict, dict]] = {
    "Sistema": (_MAC_CLARO, _MAC_ESCURO),
    "Holográfico": (_HOLO_CLARO, _HOLO_ESCURO),
    "Grafite": (
        dict(_MAC_CLARO, fundo="#E8E8ED", destaque="#48484A",
             grupos=dict.fromkeys(GRUPOS, "#636366")),
        dict(_MAC_ESCURO, fundo="#111113", superficie="#232325", destaque="#8E8E93",
             grupos=dict.fromkeys(GRUPOS, "#48484A")),
    ),
    "Azul Mac": (
        dict(_MAC_CLARO, grupos={"Imagem": "#5AC8FA", "Documento": "#007AFF", "Texto e dados": "#5856D6",
                                 "Áudio": "#32ADE6", "Vídeo": "#0040DD"}),
        dict(_MAC_ESCURO, grupos={"Imagem": "#64D2FF", "Documento": "#0A84FF", "Texto e dados": "#5E5CE6",
                                  "Áudio": "#40C8E0", "Vídeo": "#409CFF"}),
    ),
    "Rosa": (
        dict(_MAC_CLARO, fundo="#FFF5F7", destaque="#FF2D55",
             grupos={"Imagem": "#FF2D55", "Documento": "#D6336C", "Texto e dados": "#FF6482",
                     "Áudio": "#AF52DE", "Vídeo": "#C2185B"}),
        dict(_MAC_ESCURO, fundo="#1E1418", destaque="#FF375F",
             grupos={"Imagem": "#FF375F", "Documento": "#E64980", "Texto e dados": "#FF6482",
                     "Áudio": "#BF5AF2", "Vídeo": "#D6336C"}),
    ),
    "Verde": (
        dict(_MAC_CLARO, fundo="#F3FAF5", destaque="#248A3D",
             grupos={"Imagem": "#34C759", "Documento": "#248A3D", "Texto e dados": "#00C7BE",
                     "Áudio": "#30B0C7", "Vídeo": "#1E7A34"}),
        dict(_MAC_ESCURO, fundo="#101A13", destaque="#30D158",
             grupos={"Imagem": "#30D158", "Documento": "#32D74B", "Texto e dados": "#63E6E2",
                     "Áudio": "#40C8E0", "Vídeo": "#248A3D"}),
    ),
}


@dataclass(frozen=True)
class Aparencia:
    """O que o usuário escolheu (o que vai para o arquivo)."""

    tema: str = "Sistema"
    modo: str = "auto"            # auto = segue o claro/escuro do sistema
    destaque: str | None = None   # None = cor do tema
    fundo: str | None = None
    cores_grupo: dict = field(default_factory=dict)
    opacidade: float = 0.96       # do fundo do painel, 0.6 a 1.0
    tamanho: str = "M"
    forma: str = "radial"
    moldura_windows: bool = False  # True = usar a moldura padrão do Windows na janela principal


PADRAO = Aparencia()


def validar(a: Aparencia) -> list[str]:
    erros = []
    if a.tema not in PRESETS:
        erros.append(f"Tema desconhecido: {a.tema}.")
    if a.modo not in MODOS:
        erros.append(f"Modo desconhecido: {a.modo}.")
    if a.tamanho not in TAMANHOS:
        erros.append(f"Tamanho desconhecido: {a.tamanho}.")
    if a.forma not in FORMAS:
        erros.append(f"Forma desconhecida: {a.forma}.")
    if not 0.6 <= float(a.opacidade) <= 1.0:
        erros.append("Transparência fora do intervalo (opacidade de 60% a 100%).")
    for nome, cor in [("destaque", a.destaque), ("fundo", a.fundo), *a.cores_grupo.items()]:
        if cor is not None and not _HEX.match(str(cor)):
            erros.append(f"Cor inválida em {nome}: {cor} (use o formato #RRGGBB).")
    for g in a.cores_grupo:
        if g not in GRUPOS:
            erros.append(f"Grupo desconhecido: {g}.")
    return erros


# ---------- claro/escuro do sistema ----------

def sistema_escuro() -> bool:
    """True se o sistema está no modo escuro. Em caso de dúvida, claro."""
    try:
        if sys.platform == "win32":
            import winreg

            chave = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return r.stdout.strip().lower() == "dark"
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def paleta(a: Aparencia, escuro: bool | None = None) -> Paleta:
    if escuro is None:
        escuro = {"claro": False, "escuro": True}.get(a.modo)
        if escuro is None:
            escuro = sistema_escuro()
    base = PRESETS.get(a.tema, PRESETS["Sistema"])[1 if escuro else 0]
    grupos = dict(base["grupos"])
    grupos.update({g: c for g, c in a.cores_grupo.items() if g in GRUPOS})
    return Paleta(
        fundo=a.fundo or base["fundo"],
        superficie=base["superficie"],
        texto=base["texto"],
        texto_sec=base["texto_sec"],
        destaque=a.destaque or base["destaque"],
        grupos=grupos,
        escuro=escuro,
        efeito=base.get("efeito", ""),
    )


# ---------- contraste (WCAG 2.x) ----------

def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def luminancia(h: str) -> float:
    def canal(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def texto_sobre(fundo: str, minimo_branco: float = 3.0) -> str:
    """Cor do texto sobre um fundo colorido. Como no macOS, prefere branco
    (ex.: botão azul) quando o contraste chega a 3:1; senão, o de maior contraste."""
    if contraste("#FFFFFF", fundo) >= minimo_branco:
        return "#FFFFFF"
    return "#FFFFFF" if contraste("#FFFFFF", fundo) >= contraste("#1D1D1F", fundo) else "#1D1D1F"


def legivel(cor: str, fundo: str, minimo: float = 4.5) -> str:
    """Mesma cor, escurecida (fundo claro) ou clareada (fundo escuro) até ter
    contraste mínimo com o fundo. Mantém o tom; só ajusta a luminosidade."""
    alvo = (0, 0, 0) if luminancia(fundo) > 0.5 else (255, 255, 255)
    r, g, b = _rgb(cor)
    for i in range(21):
        t = i / 20
        c = "#" + "".join(f"{round(v + (a - v) * t):02X}" for v, a in zip((r, g, b), alvo))
        if contraste(c, fundo) >= minimo:
            return c
    return "#000000" if alvo == (0, 0, 0) else "#FFFFFF"


# ---------- arquivo ----------

def arquivo() -> Path:
    from conversor.atalho.config import pasta_config

    return pasta_config() / "aparencia.json"


def carregar(caminho: Path | None = None) -> Aparencia:
    caminho = caminho or arquivo()
    if not caminho.is_file():
        return PADRAO
    try:
        d = json.loads(caminho.read_text(encoding="utf-8"))
        a = Aparencia(**{k: v for k, v in d.items() if k in Aparencia.__dataclass_fields__})
        a = replace(a, opacidade=float(a.opacidade), cores_grupo=dict(a.cores_grupo or {}))
        erros = validar(a)
        if erros:
            raise ValueError("; ".join(erros))
        return a
    except Exception as e:
        reserva = caminho.with_suffix(".json.corrompido")
        try:
            os.replace(caminho, reserva)
        except OSError:
            pass
        get_logger().warning("aparência inválida (%s); usando o padrão. Cópia em %s", e, reserva)
        return PADRAO


def salvar(a: Aparencia, caminho: Path | None = None) -> None:
    erros = validar(a)
    if erros:
        raise ValueError("; ".join(erros))
    caminho = caminho or arquivo()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(a), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)
