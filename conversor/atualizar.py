"""Atualizar o Lotus pela última versão publicada no GitHub (Releases).

PRIVACIDADE (regra 8, revisada): esta é a ÚNICA parte do Lotus que usa a
internet, e só quando a pessoa pede (Ferramentas → Procurar atualização, ou
"Sim" no lembrete mensal, que apenas pergunta). Nenhum dado do usuário é
enviado: o GitHub recebe o IP e o "User-Agent: Lotus/<versão>", como em
qualquer acesso a um site. Nada de telemetria.

Fluxo: consultar a última Release → comparar versões → baixar o instalador do
sistema → conferir o SHA-256 publicado → (pessoa confirma) fechar, instalar
por cima e reabrir. As configurações ficam fora da pasta do programa
(%APPDATA%\\Lotus, ~/Library/Application Support/Lotus) e não são tocadas.

- Windows: LotusSetup.exe /VERYSILENT … /atualizacao=1. Com esse parâmetro o
  instalador NÃO reaplica as opções da 1ª instalação (painel, ícone, menu):
  só refaz caminhos e reabre o Lotus (installer/lotus.iss).
- Mac: monta o .dmg, copia o Lotus.app para perto do atual e um script troca
  os dois depois que o Lotus fechar, e reabre.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from conversor import __version__
from conversor.logs import get_logger

REPO = "Kiuwar/Lotus"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
HOSTS_PERMITIDOS = ("api.github.com", "github.com", "objects.githubusercontent.com",
                    "release-assets.githubusercontent.com")
LEMBRETE_DIAS = 30
TEMPO_LIMITE = 30  # s por requisição


class ErroAtualizacao(Exception):
    pass


@dataclass
class Versao:
    numero: str
    notas: str
    arquivo: str          # nome do instalador deste sistema
    url: str
    sha256: str | None
    tamanho: int = 0


# ---------- lógica pura ----------

def versao_tupla(v: str) -> tuple[int, ...]:
    partes = re.findall(r"\d+", v.lstrip("vV").split("-")[0])
    return tuple(int(p) for p in partes[:3]) or (0,)


def e_mais_nova(remota: str, local: str = __version__) -> bool:
    return versao_tupla(remota) > versao_tupla(local)


def nome_do_instalador(sistema: str | None = None, maquina: str | None = None) -> str:
    sistema = sistema or sys.platform
    maquina = (maquina or platform.machine()).lower()
    if sistema == "win32":
        return "LotusSetup.exe"
    if sistema == "darwin":
        return "Lotus-Mac-AppleSilicon.dmg" if maquina in ("arm64", "aarch64") else "Lotus-Mac-Intel.dmg"
    raise ErroAtualizacao("Atualização automática só existe no Windows e no Mac.")


def ler_somas(texto: str) -> dict[str, str]:
    """Linhas "<sha256>  <caminho>" (SHA256SUMS.txt ou as notas da Release)."""
    somas = {}
    for m in re.finditer(r"\b([0-9a-fA-F]{64})\s+\*?([^\s]+)", texto):
        somas[m.group(2).rsplit("/", 1)[-1]] = m.group(1).lower()
    return somas


def escolher(release: dict, sistema: str | None = None, maquina: str | None = None,
             somas_extra: str = "") -> Versao:
    nome = nome_do_instalador(sistema, maquina)
    ativos = {a.get("name"): a for a in release.get("assets", [])}
    if nome not in ativos:
        raise ErroAtualizacao(f"A versão {release.get('tag_name')} não tem o arquivo {nome}.")
    somas = ler_somas((release.get("body") or "") + "\n" + somas_extra)
    a = ativos[nome]
    return Versao(numero=str(release.get("tag_name", "")).lstrip("vV"), notas=release.get("body") or "",
                  arquivo=nome, url=a.get("browser_download_url", ""), sha256=somas.get(nome),
                  tamanho=int(a.get("size") or 0))


def url_segura(url: str) -> bool:
    from urllib.parse import urlparse

    u = urlparse(url)
    return u.scheme == "https" and (u.hostname or "") in HOSTS_PERMITIDOS


def conferir(arquivo: Path, esperado: str | None) -> None:
    """Apaga o arquivo e explica se o SHA-256 não bate (download corrompido ou trocado)."""
    if not esperado:
        arquivo.unlink(missing_ok=True)
        raise ErroAtualizacao("A versão publicada não traz o código de conferência (SHA-256); por "
                              "segurança, nada foi instalado. Como resolver: baixe pela página "
                              f"github.com/{REPO}/releases.")
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    if h.hexdigest() != esperado.lower():
        arquivo.unlink(missing_ok=True)
        raise ErroAtualizacao("O arquivo baixado não confere com o publicado (pode ter vindo "
                              "incompleto). Nada foi instalado. Como resolver: tente de novo.")


# ---------- lembrete mensal (só pergunta; não acessa a internet) ----------

def _arq_estado() -> Path:
    from conversor.atalho.config import pasta_config

    return pasta_config() / "atualizacao.json"


def _ler_estado() -> dict:
    try:
        return json.loads(_arq_estado().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_estado(d: dict) -> None:
    p = _arq_estado()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def deve_lembrar(hoje: dt.date | None = None) -> bool:
    """True uma vez a cada 30 dias. Na 1ª abertura só marca a data (não incomoda)."""
    hoje = hoje or dt.date.today()
    estado = _ler_estado()
    try:
        ultima = dt.date.fromisoformat(estado["ultima_pergunta"])
    except (KeyError, ValueError):
        estado["ultima_pergunta"] = hoje.isoformat()
        _gravar_estado(estado)
        return False
    return (hoje - ultima).days >= LEMBRETE_DIAS


def lembrete_respondido(hoje: dt.date | None = None) -> None:
    estado = _ler_estado()
    estado["ultima_pergunta"] = (hoje or dt.date.today()).isoformat()
    _gravar_estado(estado)


# ---------- rede (só quando a pessoa pede) ----------

def _contexto_ssl():
    import ssl

    if sys.platform == "darwin":
        # O Python empacotado no Mac não enxerga os certificados do sistema.
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
    return ssl.create_default_context()


def _abrir(url: str):
    import urllib.request

    if not url_segura(url):
        raise ErroAtualizacao(f"Endereço inesperado: {url}")
    pedido = urllib.request.Request(url, headers={"User-Agent": f"Lotus/{__version__}",
                                                  "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE, context=_contexto_ssl())


def _explicar_rede(e: Exception) -> ErroAtualizacao:
    return ErroAtualizacao(f"Não foi possível falar com o GitHub ({e}). Como resolver: confira a "
                           "internet e tente de novo; se usar proxy ou firewall, libere github.com.")


def procurar(abrir=_abrir, sistema: str | None = None) -> Versao | None:
    """A versão publicada mais nova, ou None se esta já é a mais recente."""
    try:
        with abrir(URL_ULTIMA) as r:
            release = json.loads(r.read().decode("utf-8"))
    except ErroAtualizacao:
        raise
    except Exception as e:  # noqa: BLE001 - rede: vira mensagem com "Como resolver"
        raise _explicar_rede(e) from e
    if not e_mais_nova(str(release.get("tag_name", "0"))):
        return None
    extra = ""
    soma = next((a for a in release.get("assets", []) if a.get("name") == "SHA256SUMS.txt"), None)
    if soma:
        try:
            with abrir(soma["browser_download_url"]) as r:
                extra = r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - as notas da Release também trazem as somas
            get_logger().exception("SHA256SUMS.txt")
    return escolher(release, sistema, somas_extra=extra)


def pasta_downloads() -> Path:
    from conversor.atalho.config import pasta_config

    return pasta_config() / "atualizacao"


def baixar(v: Versao, progresso=lambda feito, total: None, abrir=_abrir,
           cancelado=lambda: False) -> Path:
    destino = pasta_downloads() / v.arquivo
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():  # baixado antes ("Depois"): reaproveita se ainda conferir
        try:
            conferir(destino, v.sha256)
            return destino
        except ErroAtualizacao:
            pass  # conferir() já apagou o arquivo velho
    parcial =destino.with_suffix(destino.suffix + ".parcial")
    try:
        with abrir(v.url) as r, open(parcial, "wb") as f:
            total = int(r.headers.get("Content-Length") or v.tamanho or 0)
            feito = 0
            while True:
                if cancelado():
                    raise ErroAtualizacao("Download cancelado.")
                bloco = r.read(1 << 16)
                if not bloco:
                    break
                f.write(bloco)
                feito += len(bloco)
                progresso(feito, total)
    except ErroAtualizacao:
        parcial.unlink(missing_ok=True)
        raise
    except Exception as e:  # noqa: BLE001
        parcial.unlink(missing_ok=True)
        raise _explicar_rede(e) from e
    os.replace(parcial, destino)
    conferir(destino, v.sha256)
    return destino


# ---------- aplicar (fecha, instala por cima, reabre) ----------

def comando_windows(instalador: Path, log: Path) -> list[str]:
    return [str(instalador), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/atualizacao=1",
            f"/LOG={log}"]


def pacote_atual() -> Path:
    exe = Path(sys.executable).resolve()
    for p in exe.parents:
        if p.suffix == ".app":
            return p
    raise ErroAtualizacao("Este Lotus não está rodando de um Lotus.app (versão de desenvolvimento): "
                          "atualize pelo git.")


def script_mac(pid: int, atual: Path, novo: Path, reabrir: str = "open") -> str:
    """Espera o Lotus fechar, troca o .app (guardando o antigo até dar certo) e reabre."""
    a, n, velho = shlex.quote(str(atual)), shlex.quote(str(novo)), shlex.quote(str(atual) + ".antigo")
    return f"""#!/bin/sh
# Gerado pelo Lotus para concluir a atualização.
i=0
while kill -0 {pid} 2>/dev/null && [ $i -lt 120 ]; do sleep 0.5; i=$((i+1)); done
rm -rf {velho}
if mv {a} {velho} && mv {n} {a}; then
  rm -rf {velho}
else
  [ -d {velho} ] && [ ! -d {a} ] && mv {velho} {a}
fi
{reabrir} {a}
"""


def preparar_mac(dmg: Path, atual: Path | None = None) -> Path:
    """Copia o Lotus.app do .dmg para ao lado do atual. Devolve o caminho do novo."""
    atual = atual or pacote_atual()
    if not os.access(atual.parent, os.W_OK):
        raise ErroAtualizacao(f"Sem permissão para gravar em {atual.parent}. Como resolver: abra o "
                              f"{dmg.name} (em {dmg.parent}) e arraste o Lotus para Aplicativos.")
    ponto = Path(tempfile.mkdtemp(prefix="lotus-dmg-"))
    novo = atual.with_name(".Lotus-novo.app")
    subprocess.run(["rm", "-rf", str(novo)], check=False)
    r = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(ponto), str(dmg)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ErroAtualizacao(f"Não foi possível abrir o {dmg.name}: {r.stderr.strip()}")
    try:
        origem = ponto / "Lotus.app"
        if not origem.is_dir():
            raise ErroAtualizacao(f"O {dmg.name} não contém o Lotus.app.")
        r = subprocess.run(["ditto", str(origem), str(novo)], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise ErroAtualizacao(f"Falha ao copiar o novo Lotus: {r.stderr.strip()}")
    finally:
        subprocess.run(["hdiutil", "detach", str(ponto), "-quiet"], check=False, timeout=60)
    return novo


def aplicar(arquivo: Path) -> None:
    """Dispara a instalação e devolve: quem chamou deve fechar o Lotus em seguida."""
    from conversor.atalho import controle

    log = get_logger()
    controle.parar_agente()  # o painel em segundo plano também usa os arquivos do programa
    if sys.platform == "win32":
        registro = pasta_downloads() / "instalacao.log"
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(comando_windows(arquivo, registro), creationflags=flags, close_fds=True)
        log.info("atualização: instalador iniciado (%s)", arquivo)
        return
    if sys.platform == "darwin":
        atual = pacote_atual()
        novo = preparar_mac(arquivo, atual)
        script = pasta_downloads() / "concluir.sh"
        script.write_text(script_mac(os.getpid(), atual, novo), encoding="utf-8")
        script.chmod(0o755)
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True)
        log.info("atualização: troca do .app agendada (%s)", atual)
        return
    raise ErroAtualizacao("Atualização automática só existe no Windows e no Mac.")
