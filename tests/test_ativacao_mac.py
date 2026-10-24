"""Ativação guiada do painel no Mac (etapa A2).

A lógica dos passos, a janela (com estado simulado) e a nova tentativa do
gancho (com um Quartz falso) rodam em qualquer sistema. Abrir a seção certa
dos Ajustes do Sistema e o gesto real no Finder só podem ser testados num Mac
de verdade, por uma pessoa.
"""

from __future__ import annotations

import gc
import queue
import threading
import types

import pytest

from conversor.atalho import ativacao_mac as am
from conversor.atalho import config, mac

NOVO = {"atalho_ativo": False, "agente_rodando": False, "ax_confiavel": False,
        "estado_agente": None, "automacao": None}
PRONTO = {"atalho_ativo": True, "agente_rodando": True, "ax_confiavel": True,
          "estado_agente": {"gancho_ok": True}, "automacao": "ok"}


# ---------- passos ----------

def test_fresh_install_shows_three_pending_steps_with_buttons():
    p = am.passos(NOVO)
    assert [x.feito for x in p] == [False, False, False]
    assert [x.acao for x in p] == ["ligar", "acessibilidade", "testar_finder"]
    assert "Privacidade e Segurança → Acessibilidade" in p[1].explicacao
    assert am.resumo(NOVO) == ("Painel por atalho: desligado — clique para ativar", "desligado")


def test_everything_done():
    p = am.passos(PRONTO)
    assert am.tudo_pronto(p) and not any(x.botao for x in p)
    assert am.resumo(PRONTO) == ("Painel por atalho: pronto ✓", "ok")


def test_permission_given_but_agent_still_installing_hook():
    e = dict(PRONTO, estado_agente={"gancho_ok": False})
    p2 = am.passos(e)[1]
    assert not p2.feito and "ativando o atalho" in p2.explicacao
    texto, nivel = am.resumo(e)
    assert nivel == "aviso" and "permitir acessibilidade" in texto


def test_stale_permission_hint_appears_after_waiting():
    e = dict(NOVO, atalho_ativo=True, agente_rodando=True, segundos_desde_ajustes=5)
    assert am.passos(e)[1].dica == ""
    e["segundos_desde_ajustes"] = am.ESPERA_PERMISSAO_VELHA
    assert "clique em − (remover), depois em +" in am.passos(e)[1].dica


@pytest.mark.parametrize("auto,acao,feito", [("negado", "automacao", False), ("testando", "", False),
                                             ("ok", "", True), (None, "testar_finder", False)])
def test_finder_step_follows_automation_answer(auto, acao, feito):
    p3 = am.passos(dict(PRONTO, automacao=auto))[2]
    assert p3.acao == acao and p3.feito is feito


class _R:
    def __init__(self, code):
        self.returncode, self.stdout, self.stderr = code, "", ""


def test_open_settings_falls_back_to_privacy_page():
    chamadas = []

    def falha_primeiro(cmd, **kw):
        chamadas.append(cmd[1])
        return _R(1 if cmd[1] == am.URL_ACESSIBILIDADE else 0)

    assert am.abrir_ajustes("acessibilidade", falha_primeiro) is True
    assert chamadas == [am.URL_ACESSIBILIDADE, am.URL_PRIVACIDADE]
    assert am.abrir_ajustes("automacao", lambda c, **k: _R(1)) is False


def test_restart_rule_avoids_loops():
    assert mac.deve_reiniciar(mac.TENTATIVAS_COM_PERMISSAO, None, 1000.0)
    assert not mac.deve_reiniciar(mac.TENTATIVAS_COM_PERMISSAO - 1, None, 1000.0)
    assert not mac.deve_reiniciar(mac.TENTATIVAS_COM_PERMISSAO, 1000.0 - 10, 1000.0), \
        "reiniciou há pouco: não reinicia de novo"


def test_first_run_flag_is_saved(tmp_path):
    arq = tmp_path / "config.json"
    cfg = config.carregar(arq)
    assert cfg.guia_mac_visto is False
    cfg.guia_mac_visto = True
    config.salvar(cfg, arq)
    assert config.carregar(arq).guia_mac_visto is True


# ---------- nova tentativa do gancho (Quartz falso) ----------

def _quartz_falso(respostas: list):
    """CGEventTapCreate devolve as respostas em ordem (None = sem permissão)."""
    parar = threading.Event()
    q = types.SimpleNamespace(
        kCGEventFlagMaskControl=1, kCGEventFlagMaskShift=2, kCGEventFlagMaskAlternate=4,
        kCGEventFlagMaskCommand=8, kCGEventLeftMouseDown=1, kCGEventLeftMouseUp=2,
        kCGEventRightMouseDown=3, kCGEventRightMouseUp=4, kCGEventOtherMouseDown=25,
        kCGEventOtherMouseUp=26, kCGSessionEventTap=1, kCGHeadInsertEventTap=0,
        kCGEventTapOptionDefault=0, kCFRunLoopCommonModes="comum",
        CGEventMaskBit=lambda t: 1 << t,
        CGEventTapCreate=lambda *a: respostas.pop(0) if respostas else None,
        CFMachPortCreateRunLoopSource=lambda *a: "fonte", CFRunLoopGetCurrent=lambda: "loop",
        CFRunLoopAddSource=lambda *a: None, CGEventTapEnable=lambda *a: None,
        CFRunLoopRun=lambda: parar.wait(10), CFRunLoopStop=lambda loop: parar.set(),
    )
    return q


@pytest.fixture
def gancho(monkeypatch):
    def criar(respostas, ax=True):
        monkeypatch.setitem(__import__("sys").modules, "Quartz", _quartz_falso(respostas))
        monkeypatch.setattr(mac, "INTERVALO_TENTATIVA", 0.01)
        monkeypatch.setattr(mac, "ax_confiavel", lambda: ax)
        monkeypatch.setattr(mac, "ultimo_reinicio", lambda: None)
        avisos: queue.Queue = queue.Queue()
        g = mac.GanchoMac(config.PADRAO, queue.Queue(), avisos=avisos)
        criados.append(g)
        return g, avisos

    criados: list = []
    yield criar
    for g in criados:
        g.parar()
        g.join(2)


def test_hook_is_installed_when_permission_arrives(gancho):
    g, avisos = gancho([None, None, "tap"])
    g.start()
    assert avisos.get(timeout=3) == ("gancho_ok",)
    assert g.erro is None


def test_agent_asks_restart_when_permission_given_but_hook_keeps_failing(gancho):
    g, avisos = gancho([None] * 20)
    g.start()
    assert avisos.get(timeout=3) == ("reiniciar",)
    g.join(2)
    assert not g.is_alive()


def test_without_permission_agent_keeps_waiting_and_stops_cleanly(gancho):
    g, avisos = gancho([None] * 5, ax=False)
    g.start()
    assert g.pronto.wait(2) and g.erro == mac.MSG_SEM_ACESSIBILIDADE
    g.parar()
    g.join(2)
    assert not g.is_alive() and avisos.empty()


# ---------- janela (estado simulado) ----------

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


def test_window_updates_itself_and_runs_actions(root):
    from conversor.atalho.janela_ativacao import JanelaAtivacao

    estado = dict(NOVO)
    abertos, chamadas = [], []
    acoes = {"ligar": lambda fila: chamadas.append("ligar"),
             "testar_finder": lambda fila: (chamadas.append("finder"), fila.put(("automacao", "ok")))}
    j = JanelaAtivacao(root, coletor=lambda auto: dict(estado), acoes=acoes,
                       abrir=lambda qual: abertos.append(qual) or True)
    root.update()
    botoes = [linha[4] for linha in j.linhas]
    assert botoes[0].cget("text") == "Ligar agora" and botoes[0].winfo_manager() == "pack"

    botoes[0].invoke()
    botoes[1].invoke()
    assert chamadas == ["ligar"] and abertos == ["acessibilidade"]

    estado.update(atalho_ativo=True, agente_rodando=True, ax_confiavel=True,
                  estado_agente={"gancho_ok": True})
    botoes[2].invoke()  # testar o Finder: a resposta chega pela fila
    j.atualizar_ja()
    assert [linha[0].cget("text") for linha in j.linhas] == ["✓", "✓", "✓"]
    assert "Tudo pronto" in j.rodape.cget("text")
    assert not any(b.winfo_manager() for b in botoes), "passos prontos não têm botão"
    j.fechar()
    root.update()


def test_closing_parent_with_window_open_leaves_no_pending_after(root):
    from conversor.atalho.janela_ativacao import JanelaAtivacao

    j = JanelaAtivacao(root, coletor=lambda auto: dict(NOVO))
    root.update()
    assert j._pendente is not None
    j.destroy()
    root.update()
    assert j.fechado and j._pendente is None
