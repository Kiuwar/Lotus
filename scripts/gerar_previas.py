"""Gera as imagens de prévia do design (painel e janelas) numa pasta.

Uso (Linux precisa de display; no CI: xvfb-run):
    python scripts/gerar_previas.py previas/
Gera: painel radial/cartão em cada tema (claro/escuro), janela principal
(clara/escura) e a janela Aparência.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from conversor.ui import tema  # noqa: E402
from conversor.ui.render import salvar_galeria  # noqa: E402


def _capturar(janela: tk.Misc, destino: Path) -> None:
    janela.update()
    x, y = janela.winfo_rootx(), janela.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + janela.winfo_width(), y + janela.winfo_height())).save(destino)


def janela_principal(destino: Path, escuro: bool) -> None:
    from conversor.gui import App
    from conversor.ui.moldura import Moldura
    from tests.conftest import make_sample

    amostras = destino.parent / "_amostras"
    amostras.mkdir(exist_ok=True)
    root = tk.Tk()
    pal = tema.paleta(tema.Aparencia(), escuro=escuro)
    m = Moldura(root, pal, "Lotus", propria=True)
    root.geometry("860x680+0+0")
    app = App(m.conteudo, pal=pal, moldura=m)
    app.add_files([str(make_sample(f, amostras)) for f in ("pdf", "png", "xlsx")])
    root.after(800, lambda: (_capturar(root, destino), root.destroy()))
    root.mainloop()


def janela_aparencia(destino: Path) -> None:
    from conversor.ui.janela_aparencia import JanelaAparencia
    from conversor.ui.widgets import aplicar_estilo_ttk

    root = tk.Tk()
    root.withdraw()
    aplicar_estilo_ttk(root, tema.paleta(tema.Aparencia(), escuro=False))
    j = JanelaAparencia(root)
    j.geometry("+0+0")
    root.after(800, lambda: (_capturar(j, destino), root.destroy()))
    root.mainloop()


def main() -> int:
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else "previas")
    pasta.mkdir(parents=True, exist_ok=True)
    salvar_galeria(pasta / "painel")
    janela_principal(pasta / "janela-clara.png", escuro=False)
    janela_principal(pasta / "janela-escura.png", escuro=True)
    janela_aparencia(pasta / "aparencia.png")
    print(f"Prévias em {pasta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
