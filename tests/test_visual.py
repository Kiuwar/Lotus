"""Janela principal estilo macOS: moldura própria, pílulas, cartões, Aparência."""

from __future__ import annotations

import gc

import pytest

tk = pytest.importorskip("tkinter")

from conversor.ui import tema  # noqa: E402


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"sem display disponível ({e})")
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass
    gc.collect()


def _pal(escuro=False):
    return tema.paleta(tema.Aparencia(), escuro=escuro)


def test_pill_button_states_and_click(root):
    from conversor.ui.widgets import BotaoPilula

    cliques = []
    b = BotaoPilula(root, "Converter", command=lambda: cliques.append(1), pal=_pal(), primario=True)
    b.pack()
    root.update()
    b.invoke()
    assert cliques == [1]
    b.configure(state="disabled")
    assert str(b["state"]) == "disabled"
    b.invoke()
    assert cliques == [1], "desabilitado não pode executar"
    b.configure(state="normal", text="Outro")
    assert b.texto == "Outro"


def test_primary_button_uses_white_text_like_macos():
    pal = _pal()
    assert tema.texto_sobre(pal.destaque) == "#FFFFFF"


def test_rounded_rectangle_has_round_corners():
    from conversor.ui.widgets import retangulo_arredondado

    img = retangulo_arredondado(100, 40, 12, "#FF0000", "#FFFFFF")
    assert img.getpixel((0, 0))[:3] == (255, 255, 255)   # canto = fundo do pai
    assert img.getpixel((50, 20))[:3] == (255, 0, 0)      # meio = cor do botão


def _app(root, propria=True, escuro=False):
    from conversor.gui import App
    from conversor.ui.moldura import Moldura

    pal = _pal(escuro)
    m = Moldura(root, pal, "Lotus", propria=propria)
    root.geometry("860x680+0+0")
    app = App(m.conteudo, pal=pal, moldura=m)
    import time

    fim = time.time() + 5
    while not m.pronta and time.time() < fim:  # no Windows: espera a janela reaparecer
        root.update()
        time.sleep(0.02)
    root.update()
    return m, app


def test_custom_frame_has_traffic_lights_and_tools_button(root):
    m, app = _app(root)
    assert root.overrideredirect()
    assert set(m.bolinhas) == {"fechar", "minimizar", "maximizar"}
    assert m._menu is app.tools_menu
    rotulos = [app.tools_menu.entrycget(i, "label") for i in range(app.tools_menu.index("end") + 1)
               if app.tools_menu.type(i) == "command"]
    assert "Aparência…" in rotulos and "Atalho do painel flutuante…" in rotulos


def test_native_frame_keeps_menubar(root):
    m, app = _app(root, propria=False)
    assert not root.overrideredirect()
    assert root.cget("menu"), "sem moldura própria, o menu Ferramentas fica na barra nativa"


def test_maximize_toggles_and_restores(root):
    m, _ = _app(root)
    antes = root.geometry()
    m.acao("maximizar")
    root.update()
    assert m.maximizada and root.winfo_width() >= 860
    m.acao("maximizar")
    root.update()
    assert not m.maximizada and root.geometry() == antes


def test_drag_title_bar_moves_window(root):
    m, _ = _app(root)

    class Ev:
        def __init__(self, x, y):
            self.x_root, self.y_root = x, y

    x0, y0 = root.winfo_x(), root.winfo_y()
    m._arraste = (10, 10)
    m._arrastar(Ev(x0 + 110, y0 + 60))
    root.update()
    assert (root.winfo_x(), root.winfo_y()) == (x0 + 100, y0 + 50)


def test_resize_grip_respects_minimum(root):
    m, _ = _app(root)

    class Ev:
        def __init__(self, x, y):
            self.x_root, self.y_root = x, y

    m._inicio_redim(Ev(0, 0))
    m._redimensionar(Ev(-5000, -5000))
    root.update()
    mw, ma = root.minsize()
    assert root.winfo_width() >= mw and root.winfo_height() >= ma


def test_dark_theme_applies_to_main_window(root):
    _, app = _app(root, escuro=True)
    assert app.log.cget("bg").upper() == _pal(True).superficie
    assert app.convert_btn.primario


def test_close_button_destroys_window():
    r = tk.Tk()
    m, _ = _app(r)
    m.acao("fechar")
    with pytest.raises(tk.TclError):
        r.winfo_exists()


# ---------- janela Aparência ----------

def test_appearance_window_preview_and_save(root, monkeypatch):
    from conversor.ui import janela_aparencia as mod

    monkeypatch.setattr(mod.messagebox, "showinfo", lambda *a, **k: None)
    j = mod.JanelaAparencia(root)
    root.update()
    assert j.aparencia() == tema.carregar()
    img1 = j.imagem_previa()

    j.v_tema.set("Rosa")
    j.v_forma.set("cartao")
    j.v_tamanho.set("G")
    j.v_opac.set(80)
    j.definir_cor("Imagem", "#00AA00")
    j.definir_cor("destaque", "#112233")
    img2 = j.imagem_previa()
    assert img2.size != img1.size, "prévia muda com tamanho/forma"

    j.salvar()
    salvo = tema.carregar()
    assert (salvo.tema, salvo.forma, salvo.tamanho, salvo.opacidade) == ("Rosa", "cartao", "G", 0.8)
    assert salvo.cores_grupo == {"Imagem": "#00AA00"} and salvo.destaque == "#112233"
    tema.salvar(tema.PADRAO)  # não contaminar os outros testes


def test_appearance_reset_and_color_reset(root):
    from conversor.ui.janela_aparencia import JanelaAparencia

    j = JanelaAparencia(root)
    j.definir_cor("Vídeo", "#123456")
    j.definir_cor("Vídeo", None)
    assert "Vídeo" not in j.aparencia().cores_grupo
    j.v_tema.set("Verde")
    j.padrao()
    assert j.aparencia() == tema.PADRAO
    j.destroy()
