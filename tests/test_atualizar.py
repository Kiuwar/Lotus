"""Atualizar: versões, escolha do instalador, conferência SHA-256, lembrete
mensal e a troca do app no Mac. A rede é SIMULADA: nenhum teste acessa a internet."""

from __future__ import annotations

import datetime as dt
import gc
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conversor import __version__, atualizar


def _release(tag="v9.9.9", corpo=None, extras=()):
    exe, dmg_a, dmg_i = b"instalador windows", b"dmg arm", b"dmg intel"
    somas = "\n".join(f"{hashlib.sha256(c).hexdigest()}  pasta/{n}" for n, c in
                      (("LotusSetup.exe", exe), ("Lotus-Mac-AppleSilicon.dmg", dmg_a),
                       ("Lotus-Mac-Intel.dmg", dmg_i)))
    ativos = [{"name": n, "size": len(c), "browser_download_url": f"https://github.com/Kiuwar/Lotus/releases/download/{tag}/{n}"}
              for n, c in (("LotusSetup.exe", exe), ("Lotus-Mac-AppleSilicon.dmg", dmg_a),
                           ("Lotus-Mac-Intel.dmg", dmg_i))]
    return {"tag_name": tag, "body": corpo if corpo is not None else f"Novidades.\n\nSHA-256:\n{somas}\n",
            "assets": ativos + list(extras)}, {"LotusSetup.exe": exe, "Lotus-Mac-AppleSilicon.dmg": dmg_a,
                                               "Lotus-Mac-Intel.dmg": dmg_i}


class _Resp(io.BytesIO):
    def __init__(self, dados: bytes):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _rede(release, conteudos, chamadas=None):
    def abrir(url):
        assert atualizar.url_segura(url), url
        if chamadas is not None:
            chamadas.append(url)
        if url == atualizar.URL_ULTIMA:
            return _Resp(json.dumps(release).encode())
        return _Resp(conteudos[url.rsplit("/", 1)[-1]])
    return abrir


# ---------- versões e escolha ----------

@pytest.mark.parametrize("remota,local,nova", [("v0.8.0", "0.7.0", True), ("0.7.0", "0.7.0", False),
                                               ("v0.10.0", "0.9.3", True), ("v0.7.1", "0.8.0", False)])
def test_version_comparison(remota, local, nova):
    assert atualizar.e_mais_nova(remota, local) is nova


@pytest.mark.parametrize("sistema,maquina,arquivo", [("win32", "AMD64", "LotusSetup.exe"),
                                                     ("darwin", "arm64", "Lotus-Mac-AppleSilicon.dmg"),
                                                     ("darwin", "x86_64", "Lotus-Mac-Intel.dmg")])
def test_right_installer_for_each_system(sistema, maquina, arquivo):
    rel, _ = _release()
    v = atualizar.escolher(rel, sistema, maquina)
    assert v.arquivo == arquivo and v.numero == "9.9.9" and len(v.sha256) == 64
    assert v.url.endswith("/" + arquivo)


def test_checksums_from_the_release_notes_format_of_0_7():
    """As notas da 0.7.0 trazem "sha  LotusSetup/LotusSetup.exe"."""
    s = atualizar.ler_somas("SHA-256:\n    " + "a" * 64 + "  LotusSetup/LotusSetup.exe\n")
    assert s == {"LotusSetup.exe": "a" * 64}


def test_only_github_https_addresses_are_accepted():
    assert atualizar.url_segura("https://github.com/Kiuwar/Lotus/releases/download/v1/LotusSetup.exe")
    assert not atualizar.url_segura("http://github.com/x")
    assert not atualizar.url_segura("https://exemplo.com/LotusSetup.exe")


# ---------- procurar e baixar (rede simulada) ----------

def test_search_reports_new_version():
    rel, cont = _release()
    v = atualizar.procurar(abrir=_rede(rel, cont), sistema="win32")
    assert v.numero == "9.9.9" and v.arquivo == "LotusSetup.exe"


def test_search_says_up_to_date(monkeypatch):
    rel, cont = _release(tag="v" + __version__)
    assert atualizar.procurar(abrir=_rede(rel, cont)) is None


def test_network_failure_explains_how_to_fix():
    def falha(url):
        raise OSError("sem conexão")

    with pytest.raises(atualizar.ErroAtualizacao, match="Como resolver"):
        atualizar.procurar(abrir=falha)


def test_download_is_verified_and_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(atualizar, "pasta_downloads", lambda: tmp_path)
    rel, cont = _release()
    v = atualizar.escolher(rel, "win32")
    chamadas, progresso = [], []
    p = atualizar.baixar(v, progresso=lambda f, t: progresso.append((f, t)), abrir=_rede(rel, cont, chamadas))
    assert p.read_bytes() == cont["LotusSetup.exe"] and progresso[-1][0] == len(cont["LotusSetup.exe"])
    atualizar.baixar(v, abrir=_rede(rel, cont, chamadas))
    assert len(chamadas) == 1, "o arquivo já conferido não é baixado de novo"


def test_tampered_download_is_deleted_and_nothing_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(atualizar, "pasta_downloads", lambda: tmp_path)
    rel, cont = _release()
    v = atualizar.escolher(rel, "win32")
    cont["LotusSetup.exe"] = b"outro conteudo"
    with pytest.raises(atualizar.ErroAtualizacao, match="não confere"):
        atualizar.baixar(v, abrir=_rede(rel, cont))
    assert not list(tmp_path.iterdir()), "nada fica na pasta"


def test_release_without_checksum_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(atualizar, "pasta_downloads", lambda: tmp_path)
    rel, cont = _release(corpo="sem somas")
    v = atualizar.escolher(rel, "win32")
    with pytest.raises(atualizar.ErroAtualizacao, match="SHA-256"):
        atualizar.baixar(v, abrir=_rede(rel, cont))


# ---------- lembrete mensal ----------

def test_monthly_reminder_only_asks_after_30_days(tmp_path, monkeypatch):
    monkeypatch.setattr(atualizar, "_arq_estado", lambda: tmp_path / "atualizacao.json")
    hoje = dt.date(2026, 10, 24)
    assert atualizar.deve_lembrar(hoje) is False, "1ª abertura: só marca a data"
    assert atualizar.deve_lembrar(hoje + dt.timedelta(days=29)) is False
    assert atualizar.deve_lembrar(hoje + dt.timedelta(days=30)) is True
    atualizar.lembrete_respondido(hoje + dt.timedelta(days=30))
    assert atualizar.deve_lembrar(hoje + dt.timedelta(days=31)) is False


# ---------- aplicar ----------

def test_windows_update_command_keeps_user_choices(tmp_path):
    cmd = atualizar.comando_windows(tmp_path / "LotusSetup.exe", tmp_path / "log.txt")
    assert cmd[1:5] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/atualizacao=1"]


def test_installer_skips_first_install_options_on_update():
    iss = (Path(__file__).parent.parent / "installer" / "lotus.iss").read_text(encoding="utf-8")
    for par in ("--ativar-atalho", "--ativar-bandeja", "--desativar-bandeja", "--instalar-menu"):
        linha = next(l for l in iss.splitlines() if par in l)
        assert "Check: InstalacaoNova" in linha, f"{par} não pode rodar na atualização"
    assert "--pos-atualizacao" in iss and "{param:atualizacao|0}" in iss


def test_settings_live_outside_the_program_folder():
    from conversor.atalho import config
    from conversor.logs import log_dir

    programa = Path(sys.executable).resolve().parent
    for pasta in (config.pasta_config(), log_dir()):
        assert programa not in pasta.resolve().parents, "a atualização troca a pasta do programa"


@pytest.mark.skipif(sys.platform == "win32", reason="script de shell (Mac); roda também no Linux")
def test_mac_swap_script_replaces_app_and_relaunches(tmp_path):
    atual, novo = tmp_path / "Lotus.app", tmp_path / ".Lotus-novo.app"
    (atual / "Contents").mkdir(parents=True)
    (atual / "Contents" / "versao").write_text("velha")
    (novo / "Contents").mkdir(parents=True)
    (novo / "Contents" / "versao").write_text("nova")
    terminou = subprocess.Popen([sys.executable, "-c", "pass"])
    terminou.wait()
    reaberto = tmp_path / "reaberto.txt"
    script = atualizar.script_mac(terminou.pid, atual, novo, reabrir=f"echo > {reaberto}; true")
    (tmp_path / "s.sh").write_text(script)
    subprocess.run(["/bin/sh", str(tmp_path / "s.sh")], check=True, timeout=30)
    assert (atual / "Contents" / "versao").read_text() == "nova"
    assert not novo.exists() and not (tmp_path / "Lotus.app.antigo").exists()
    assert reaberto.exists()


# ---------- janela (rede simulada) ----------

tk = pytest.importorskip("tkinter")


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass
    gc.collect()


def _esperar(root, cond, limite=5.0):
    import time

    fim = time.time() + limite
    while time.time() < fim and not cond():
        root.update()
        time.sleep(0.02)
    assert cond()


def test_update_window_full_flow(root, tmp_path):
    from conversor.ui.janela_atualizacao import JanelaAtualizacao

    rel, cont = _release()
    versao = atualizar.escolher(rel, "win32")
    aplicados, reiniciou = [], []
    arquivo = tmp_path / "LotusSetup.exe"

    def baixar(v, progresso, cancelado):
        progresso(5, 10)
        arquivo.write_bytes(b"x")
        return arquivo

    j = JanelaAtualizacao(root, ao_reiniciar=lambda: reiniciou.append(True),
                          procurar=lambda: versao, baixar=baixar, aplicar=aplicados.append)
    assert "nenhum arquivo ou dado seu é enviado" in j.msg.cget("text").lower()
    j.b_principal.invoke()                       # Procurar agora
    _esperar(root, lambda: j.estado == "disponivel")
    assert "9.9.9" in j.msg.cget("text") and "configurações" in j.msg.cget("text")
    j.b_principal.invoke()                       # Baixar e instalar
    _esperar(root, lambda: j.estado == "pronto")
    assert j.b_principal.cget("text") == "Reiniciar agora"
    j.b_principal.invoke()                       # Reiniciar agora
    _esperar(root, lambda: reiniciou)
    assert aplicados == [arquivo] and j.fechado


def test_update_window_shows_error_and_up_to_date(root):
    from conversor.ui.janela_atualizacao import JanelaAtualizacao

    def falha():
        raise atualizar.ErroAtualizacao("Sem internet. Como resolver: tente de novo.")

    j = JanelaAtualizacao(root, ao_reiniciar=lambda: None, procurar=falha, ja_autorizado=True)
    _esperar(root, lambda: j.estado == "erro")
    assert "Como resolver" in j.msg.cget("text") and j.b_principal.cget("text") == "Tentar de novo"
    j.fechar()
    j2 = JanelaAtualizacao(root, ao_reiniciar=lambda: None, procurar=lambda: None, ja_autorizado=True)
    _esperar(root, lambda: j2.estado == "atualizado")
    assert "mais recente" in j2.msg.cget("text")
    j2.destroy()
    root.update()
    assert j2._pendente is None
