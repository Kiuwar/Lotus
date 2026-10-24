"""Abre a janela principal e o painel no Mac e tira um print (CI, diagnóstico).

O macOS pode exigir permissão de "Gravação de Tela"; sem ela o print sai só
com o papel de parede — por isso é diagnóstico, não teste.
Uso: python scripts/capturar_mac.py saida.png
"""

import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversor.atalho.painel import Painel  # noqa: E402
from conversor.gui import App  # noqa: E402
from conversor.ui import tema  # noqa: E402
from conversor.ui.moldura import Moldura  # noqa: E402
from tests.conftest import make_sample  # noqa: E402

destino = Path(sys.argv[1])
amostras = destino.parent / "_amostras"
amostras.mkdir(parents=True, exist_ok=True)
root = tk.Tk()
pal = tema.paleta(tema.carregar())
m = Moldura(root, pal, "Lotus", propria=False)  # no Mac: moldura nativa
root.geometry("860x680+40+60")
app = App(m.conteudo, pal=pal, moldura=m)
arquivos = [str(make_sample(f, amostras)) for f in ("pdf", "png")]
app.add_files(arquivos)
root.after(700, lambda: Painel(root, arquivos[:1], 1100, 400))


def tirar():
    root.update()
    subprocess.run(["screencapture", "-x", str(destino)], check=False)
    root.destroy()


root.after(2500, tirar)
root.mainloop()
print(f"captura: {destino} ({destino.stat().st_size if destino.exists() else 0} bytes)")
