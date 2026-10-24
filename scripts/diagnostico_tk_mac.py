"""Diagnóstico do Tk no Mac: qual passo do painel trava o `update()`.

Cada cenário roda num processo separado, com limite de tempo; se travar, o
faulthandler imprime a pilha e o processo sai. Uso (CI do Mac):

    python scripts/diagnostico_tk_mac.py
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

BASE = """
import faulthandler, sys, time, tkinter as tk
faulthandler.dump_traceback_later(20, exit=True)
def girar(root, s=1.5):
    fim = time.time() + s
    while time.time() < fim:
        root.update()
        time.sleep(0.03)
root = tk.Tk()
root.withdraw()
"""

CENARIOS = {
    "1 Tk + update": "girar(root)",
    "2 Toplevel sem borda + topmost": """
top = tk.Toplevel(root); top.overrideredirect(True); top.attributes("-topmost", True)
top.geometry("200x200+300+300"); girar(root)
""",
    "3 + janela transparente": """
top = tk.Toplevel(root); top.overrideredirect(True); top.attributes("-topmost", True)
top.attributes("-transparent", True); top.configure(bg="systemTransparent")
c = tk.Canvas(top, width=200, height=200, bg="systemTransparent", highlightthickness=0); c.pack()
top.geometry("200x200+300+300"); girar(root)
""",
    "4 + focus_force": """
top = tk.Toplevel(root); top.overrideredirect(True); top.attributes("-topmost", True)
top.geometry("200x200+300+300"); top.focus_force(); girar(root)
""",
    "5 + winfo_pointerxy em loop": """
top = tk.Toplevel(root); top.overrideredirect(True); top.geometry("200x200+300+300")
def r():
    top.winfo_pointerxy(); top.after(30, r)
r(); girar(root)
""",
    "6 + PhotoImage trocada a cada 30 ms": """
from PIL import Image, ImageTk
top = tk.Toplevel(root); top.overrideredirect(True)
top.attributes("-transparent", True); top.configure(bg="systemTransparent")
c = tk.Canvas(top, width=200, height=200, bg="systemTransparent", highlightthickness=0); c.pack()
top.geometry("200x200+300+300")
fotos = []
def p(i=[0]):
    i[0] += 1
    f = ImageTk.PhotoImage(Image.new("RGBA", (200, 200), (i[0] % 255, 0, 0, 128)))
    fotos[:] = [f]; c.delete("all"); c.create_image(0, 0, anchor="nw", image=f)
    top.after(30, p)
p(); girar(root)
""",
    "7 + destruir o Toplevel transparente": """
top = tk.Toplevel(root); top.overrideredirect(True)
top.attributes("-transparent", True); top.configure(bg="systemTransparent")
top.geometry("200x200+300+300"); girar(root, 0.5); top.destroy(); girar(root)
""",
    "8 Painel do Lotus (sem cliques)": """
sys.path.insert(0, %(raiz)r)
from conversor.atalho.painel import Painel
from tests.conftest import make_sample
import tempfile, pathlib
d = pathlib.Path(tempfile.mkdtemp())
p = Painel(root, [str(make_sample("png", d))], 400, 300)
girar(root, 2)
print("superficie:", type(p.superficie).__name__)
""",
    "9 Painel do Lotus convertendo PDF->TXT": """
sys.path.insert(0, %(raiz)r)
from tkinter import messagebox
messagebox.showerror = lambda *a, **k: print("showerror", a, k)
from conversor.atalho.painel import Painel
from tests.conftest import make_sample
import tempfile, pathlib
d = pathlib.Path(tempfile.mkdtemp())
p = Painel(root, [str(make_sample("pdf", d))], 400, 300)
root.update()
it = {i.fmt: i for i in p.layout.itens}["txt"]
p.converter("txt")
fim = time.time() + 15
while not p.fechado and time.time() < fim:
    root.update(); time.sleep(0.03)
print("fechado:", p.fechado, "estados:", p.estados)
""",
    "10 CPU do app parado no mainloop (3 s)": """
sys.path.insert(0, %(raiz)r)
from conversor.gui import App
from tests.conftest import make_sample
import tempfile, pathlib
root.deiconify()
app = App(root)
app.add_files([str(make_sample("png", pathlib.Path(tempfile.mkdtemp())))])
root.after(3000, root.quit)
t0 = time.process_time(); r0 = time.time()
root.mainloop()
cpu, real = time.process_time() - t0, time.time() - r0
print(f"CPU {cpu:.2f} s em {real:.2f} s ({100 * cpu / real:.0f}%) -> "
      + ("GIRANDO (bug real)" if cpu / real > 0.5 else "ocioso (normal)"))
""",
    "11 eventos que um update() processa após converter": """
sys.path.insert(0, %(raiz)r)
import _tkinter
from conversor.gui import App
from tests.conftest import make_sample
import tempfile, pathlib
app = App(root)
src = make_sample("png", pathlib.Path(tempfile.mkdtemp()))
app.add_files([str(src)]); app.target.set("JPG"); app.start()
fim = time.time() + 15
while (app.worker.is_alive() or not app.events.empty()) and time.time() < fim:
    root.update_idletasks()
    for _ in range(500):
        if not root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
            break
    time.sleep(0.05)
n, t0 = 0, time.time()
while root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT) and n < 200000:
    n += 1
print(f"um update() processaria {n} eventos em {time.time() - t0:.2f} s"
      + (" (NUNCA ESVAZIA)" if n >= 200000 else ""))
""",
}


def main() -> int:
    travados = []
    for nome, corpo in CENARIOS.items():
        codigo = BASE + textwrap.dedent(corpo.replace("%(raiz)r", repr(str(RAIZ)))) + "\nprint('FIM')\n"
        try:
            r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                               timeout=40, cwd=RAIZ)
            ok = r.returncode == 0 and "FIM" in r.stdout
            estado = "OK" if ok else f"FALHOU (código {r.returncode})"
            saida = (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired as e:
            estado, saida = "TRAVOU (40 s)", str(e.stdout or "") + str(e.stderr or "")
        print(f"=== {nome}: {estado}")
        if estado != "OK" or saida.replace("FIM", "").strip():
            print(textwrap.indent(saida[-3000:], "    "))
        if estado != "OK":
            travados.append(nome)
    print("\nResumo:", "tudo OK" if not travados else "problemas em " + ", ".join(travados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
