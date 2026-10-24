"""Ícone do Lotus na área de notificação do Windows (ao lado do relógio).

Roda numa thread própria, com a janela invisível e o laço de mensagens do
Windows. Regra 11: a thread nunca toca no tkinter; cada escolha do menu vira
um texto na fila `comandos`, que o agente (thread principal) executa.

API do pywin32 conferida no exemplo oficial do projeto
(github.com/mhammond/pywin32, win32/Demos/win32gui_taskbar.py); os nomes
usados estão em NOMES_BANDEJA e o CI do Windows confere que existem.

O Windows decide se o ícone fica visível na barra ou dentro da setinha "^":
nenhum programa pode forçar isso. O usuário arrasta o ícone para fora uma vez
ou liga em Configurações → Personalização → Barra de tarefas.
"""

from __future__ import annotations

import queue
import threading

from conversor.logs import get_logger

DICA = "Lotus — conversor de arquivos"

ABRIR, CONVERTER, ATALHO, CONFIGURAR, APARENCIA, SAIR = (
    "abrir", "converter", "atalho", "configurar", "aparencia", "sair")
_IDS = {1001: ABRIR, 1002: CONVERTER, 1003: ATALHO, 1004: CONFIGURAR, 1005: APARENCIA, 1006: SAIR}

NOMES_BANDEJA = {
    "win32gui": ["WNDCLASS", "RegisterClass", "UnregisterClass", "CreateWindow", "DestroyWindow",
                 "RegisterWindowMessage", "LoadImage", "Shell_NotifyIcon", "NIM_ADD", "NIM_DELETE",
                 "NIF_ICON", "NIF_MESSAGE", "NIF_TIP", "CreatePopupMenu", "AppendMenu",
                 "TrackPopupMenu", "SetForegroundWindow", "GetCursorPos", "PostMessage",
                 "PostQuitMessage", "PumpMessages", "DestroyMenu", "error"],
    "win32con": ["WM_USER", "WM_DESTROY", "WM_COMMAND", "WM_CLOSE", "WM_NULL", "WM_LBUTTONDBLCLK",
                 "WM_RBUTTONUP", "WS_OVERLAPPED", "WS_SYSMENU", "CW_USEDEFAULT", "IMAGE_ICON",
                 "LR_LOADFROMFILE", "MF_STRING", "MF_SEPARATOR", "MF_CHECKED", "TPM_LEFTALIGN",
                 "SM_CXSMICON", "SM_CYSMICON"],
    "win32api": ["GetModuleHandle", "GetSystemMetrics", "LOWORD"],
}


def itens_menu(atalho_ativo: bool, atalho_desc: str) -> list[tuple[int | None, str, bool]]:
    """Menu do clique direito: (id, texto, marcado); id None = separador."""
    return [
        (1001, "Abrir o Lotus", False),
        (1002, "Converter arquivos…", False),
        (None, "", False),
        (1003, f"Painel por atalho ({atalho_desc})", atalho_ativo),
        (1004, "Configurar atalho…", False),
        (1005, "Aparência…", False),
        (None, "", False),
        (1006, "Fechar o Lotus (volta ao ligar o computador)", False),
    ]


def comando_do_id(ident: int) -> str | None:
    return _IDS.get(ident)


class Bandeja(threading.Thread):
    """Ícone e menu na área de notificação. Só no Windows."""

    MSG_ICONE = 0x0400 + 20  # WM_USER + 20, como no exemplo do pywin32

    def __init__(self, comandos: queue.Queue, icone: str, atalho_ativo: bool, atalho_desc: str):
        super().__init__(name="lotus-bandeja", daemon=True)
        self.comandos = comandos
        self.icone = icone
        self.atalho_ativo = atalho_ativo
        self.atalho_desc = atalho_desc
        self.hwnd = 0
        self.pronto = threading.Event()
        self.visivel = False  # Shell_NotifyIcon(NIM_ADD) deu certo
        self.erro: str | None = None
        self.log = get_logger()

    def atualizar(self, atalho_ativo: bool, atalho_desc: str) -> None:
        # Lido só quando o menu é montado (clique direito): sem mensagem.
        self.atalho_ativo, self.atalho_desc = atalho_ativo, atalho_desc

    def run(self) -> None:
        import win32api
        import win32con
        import win32gui

        self._g, self._c, self._a = win32gui, win32con, win32api
        try:
            reinicio = win32gui.RegisterWindowMessage("TaskbarCreated")
            wc = win32gui.WNDCLASS()
            wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = "LotusBandeja"
            wc.lpfnWndProc = {
                reinicio: self._adicionar_icone,
                win32con.WM_CLOSE: lambda *_a: win32gui.DestroyWindow(self.hwnd) or 0,
                win32con.WM_DESTROY: self._ao_destruir,
                win32con.WM_COMMAND: self._ao_comando,
                self.MSG_ICONE: self._ao_icone,
            }
            try:
                win32gui.RegisterClass(wc)
            except win32gui.error as e:  # já registrada (ex.: testes): segue
                if getattr(e, "winerror", None) != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                    raise
            self.hwnd = win32gui.CreateWindow(
                wc.lpszClassName, "Lotus", win32con.WS_OVERLAPPED | win32con.WS_SYSMENU,
                0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, 0, 0, wc.hInstance, None)
            self._adicionar_icone()
        except Exception as e:  # noqa: BLE001 - sem ícone o resto do agente continua
            self.erro = f"Não foi possível mostrar o ícone ao lado do relógio: {e}"
            self.log.exception("bandeja")
            self.pronto.set()
            return
        self.pronto.set()
        win32gui.PumpMessages()

    def _adicionar_icone(self, *_args):
        g, c, a = self._g, self._c, self._a
        lado = (a.GetSystemMetrics(c.SM_CXSMICON), a.GetSystemMetrics(c.SM_CYSMICON))
        hicon = g.LoadImage(0, self.icone, c.IMAGE_ICON, lado[0], lado[1], c.LR_LOADFROMFILE)
        nid = (self.hwnd, 0, g.NIF_ICON | g.NIF_MESSAGE | g.NIF_TIP, self.MSG_ICONE, hicon, DICA)
        try:
            g.Shell_NotifyIcon(g.NIM_ADD, nid)
            self.visivel = True
        except g.error:
            # Acontece se o Explorer ainda não terminou de abrir; "TaskbarCreated" tenta de novo.
            self.log.warning("bandeja: Shell_NotifyIcon(NIM_ADD) falhou")
        return 0

    def _ao_destruir(self, *_args):
        try:
            self._g.Shell_NotifyIcon(self._g.NIM_DELETE, (self.hwnd, 0))
        except self._g.error:
            pass
        self.visivel = False
        self._g.PostQuitMessage(0)
        return 0

    def _ao_icone(self, hwnd, msg, wparam, lparam):
        c = self._c
        if lparam == c.WM_LBUTTONDBLCLK:
            self.comandos.put(ABRIR)
        elif lparam == c.WM_RBUTTONUP:
            self._mostrar_menu()
        return 1

    def _mostrar_menu(self) -> None:
        g, c = self._g, self._c
        menu = g.CreatePopupMenu()
        for ident, texto, marcado in itens_menu(self.atalho_ativo, self.atalho_desc):
            if ident is None:
                g.AppendMenu(menu, c.MF_SEPARATOR, 0, "")
            else:
                g.AppendMenu(menu, c.MF_STRING | (c.MF_CHECKED if marcado else 0), ident, texto)
        x, y = g.GetCursorPos()
        # Sem isto o menu não fecha ao clicar fora (documentado no exemplo).
        g.SetForegroundWindow(self.hwnd)
        g.TrackPopupMenu(menu, c.TPM_LEFTALIGN, x, y, 0, self.hwnd, None)
        g.PostMessage(self.hwnd, c.WM_NULL, 0, 0)
        g.DestroyMenu(menu)

    def _ao_comando(self, hwnd, msg, wparam, lparam):
        cmd = comando_do_id(self._a.LOWORD(wparam))
        if cmd:
            self.comandos.put(cmd)
        return 0

    def parar(self) -> None:
        if self.hwnd:
            self._g.PostMessage(self.hwnd, self._c.WM_CLOSE, 0, 0)
