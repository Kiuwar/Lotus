"""Diagnóstico do painel no Mac: a avaliação é lógica pura (qualquer sistema);
a coleta real (AXIsProcessTrusted, osascript, codesign) só roda no CI do Mac."""

from __future__ import annotations

import subprocess
import sys

import pytest

from conversor.atalho import diagnostico_mac as dm
from conversor.atalho import mac

so_mac = pytest.mark.skipif(sys.platform != "darwin", reason="só no Mac")

TUDO_CERTO = {
    "atalho_ativo": True, "gatilho": "⌥ Option + ⇧ Shift + clique", "agente_rodando": True,
    "inicio_registrado": '"/Applications/Lotus.app/Contents/MacOS/Lotus" --agente',
    "inicio_esperado": '"/Applications/Lotus.app/Contents/MacOS/Lotus" --agente',
    "ax_confiavel": True, "estado_agente": {"gancho_ok": True, "inicio": "24/10/2026 10:00:00"},
    "automacao": "ok", "caminho_app": "/Applications/Lotus.app", "assinatura": "desenvolvedor",
    "processo": "app", "log": "/Users/x/Library/Logs/Lotus/lotus.log",
}


def _erros(fatos: dict) -> list[dm.Item]:
    return [i for i in dm.avaliar(fatos) if i.simbolo == dm.ERRO]


def test_everything_ok_has_no_problem():
    itens = dm.avaliar(TUDO_CERTO)
    assert not [i for i in itens if i.simbolo == dm.ERRO]
    assert "Nenhum problema" in dm.texto(itens, TUDO_CERTO)


def test_fresh_install_explains_the_panel_is_off():
    """H1: logo após instalar, o painel vem desligado e nada acontece ao clicar."""
    fatos = dict(TUDO_CERTO, atalho_ativo=False, agente_rodando=False, inicio_registrado=None,
                 estado_agente=None)
    erros = _erros(fatos)
    assert erros[0].titulo.startswith("O painel por atalho está DESLIGADO")
    assert "Ferramentas → Atalho do painel flutuante" in erros[0].como_resolver
    assert len(erros) == 1, "agente parado com o painel desligado é normal, não é erro"


def test_no_accessibility_tells_where_to_enable_and_how_to_redo_stale_permission():
    """H3: com assinatura ad-hoc, a permissão de uma versão anterior não vale mais."""
    fatos = dict(TUDO_CERTO, ax_confiavel=False, assinatura="adhoc",
                 estado_agente={"gancho_ok": False, "erro": "Sem permissão", "ax_confiavel": False})
    texto = dm.texto(dm.avaliar(fatos), fatos)
    assert "Privacidade e Segurança → Acessibilidade" in texto
    assert "clique em − (remover), depois em +" in texto


def test_permission_given_after_agent_started_is_detected():
    """H5: a permissão chegou depois; o agente não tenta de novo sozinho."""
    fatos = dict(TUDO_CERTO, estado_agente={"gancho_ok": False, "erro": "Sem permissão",
                                            "ax_confiavel": False, "inicio": "24/10/2026 09:00:00"})
    erros = _erros(fatos)
    assert len(erros) == 1 and "DEPOIS que o agente começou" in erros[0].titulo
    assert "Desligue e ligue de novo o painel" in erros[0].como_resolver


def test_old_agent_without_report_is_flagged():
    itens = dm.avaliar(dict(TUDO_CERTO, estado_agente=None))
    assert any(i.simbolo == dm.ATENCAO and "não deixou relatório" in i.titulo for i in itens)


@pytest.mark.parametrize("caminho,trecho", [
    ("/Volumes/Lotus/Lotus.app", "disco .dmg"),
    ("/private/var/folders/x/AppTranslocation/ABC/d/Lotus.app", "App Translocation"),
])
def test_running_from_dmg_or_translocated_copy_is_an_error(caminho, trecho):
    erros = _erros(dict(TUDO_CERTO, caminho_app=caminho))
    assert any(trecho in e.titulo and "Aplicativos" in e.como_resolver for e in erros)


def test_finder_automation_denied():
    erros = _erros(dict(TUDO_CERTO, automacao="negado"))
    assert "-1743" in erros[0].titulo and "Automação → Lotus" in erros[0].como_resolver


def test_launch_agent_pointing_elsewhere():
    erros = _erros(dict(TUDO_CERTO, inicio_registrado='"/Users/x/Downloads/Lotus.app/Contents/MacOS/Lotus" --agente'))
    assert "aponta para outro lugar" in erros[0].titulo


def test_terminal_run_is_explained():
    erros = _erros(dict(TUDO_CERTO, ax_confiavel=False, processo="terminal"))
    assert "vale para o Terminal" in erros[0].titulo


class _R:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_automation_probe_reads_osascript_answers():
    chamadas = []

    def ok(cmd, **kw):
        chamadas.append(cmd)
        return _R(0, "2\n")

    assert dm.testar_automacao(ok) == "ok"
    assert chamadas[0] == ["osascript", "-e", dm.SCRIPT_AUTOMACAO]
    assert dm.testar_automacao(lambda c, **k: _R(1, err="execution error: Not authorized (-1743)")) == "negado"

    def demora(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 30)

    assert dm.testar_automacao(demora) == "sem_resposta"


def test_signature_kind_is_read_from_codesign():
    assert dm.assinatura("/A.app", lambda c, **k: _R(0, err="Signature=adhoc\n")) == "adhoc"
    assert dm.assinatura("/A.app", lambda c, **k: _R(0, err="Authority=Developer ID\n")) == "desenvolvedor"
    assert dm._pacote_app("/Applications/Lotus.app/Contents/MacOS/Lotus") == "/Applications/Lotus.app"


def test_agent_report_is_only_trusted_while_that_agent_runs():
    trava = mac.travar_instancia()
    assert trava is not None
    try:
        mac.gravar_estado_agente(False, "Sem permissão", False)
        estado = mac.ler_estado_agente()
        assert estado["gancho_ok"] is False and estado["erro"] == "Sem permissão"
    finally:
        trava.close()
    assert mac.ler_estado_agente() is None, "relatório de um agente que já parou não vale"


# ---------- no Mac de verdade (CI do Mac) ----------

@so_mac
def test_accessibility_api_exists_and_answers():
    import ctypes

    lib = ctypes.cdll.LoadLibrary(mac.APPLICATION_SERVICES)
    for nome in mac.NOMES_AX:
        assert hasattr(lib, nome), nome
    assert mac.ax_confiavel() in (True, False)


@so_mac
def test_real_collection_produces_a_report(monkeypatch):
    # O Finder no CI pode não responder a Automação; isso é testado à parte.
    monkeypatch.setattr(dm, "testar_automacao", lambda *a, **k: "ok")
    saida = dm.executar()
    assert saida.startswith("Diagnóstico do painel no Mac") and "Acessibilidade" in saida


@so_mac
def test_real_automation_probe_returns_an_answer():
    assert isinstance(dm.testar_automacao(limite=10), str)
