"""Imitação mínima do módulo winreg, para testar a lógica do registro no Linux.

Implementa só o que conversor/shell.py usa. O comportamento real é testado
no Windows (tests/test_shell.py::test_real_registry_roundtrip).
"""

from __future__ import annotations

HKEY_CURRENT_USER = "HKCU"
KEY_WRITE = KEY_ALL_ACCESS = KEY_READ = KEY_SET_VALUE = 0
REG_SZ = 1


class _Key:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def Close(self):
        pass


class FakeWinreg:
    HKEY_CURRENT_USER = HKEY_CURRENT_USER
    KEY_WRITE = KEY_WRITE
    KEY_ALL_ACCESS = KEY_ALL_ACCESS
    KEY_SET_VALUE = KEY_SET_VALUE
    REG_SZ = REG_SZ

    def __init__(self):
        self.keys: dict[str, dict[str, str]] = {}  # caminho minúsculo -> valores

    @staticmethod
    def _norm(path):
        return path.lower().strip("\\")

    def CreateKeyEx(self, hive, path, reserved=0, access=0):
        parts = self._norm(path).split("\\")
        for i in range(1, len(parts) + 1):  # cria os pais, como o Windows
            self.keys.setdefault("\\".join(parts[:i]), {})
        return _Key(self, self._norm(path))

    def OpenKey(self, hive, path, reserved=0, access=0):
        p = self._norm(path)
        if p not in self.keys:
            raise FileNotFoundError(path)
        return _Key(self, p)

    def SetValueEx(self, key, name, reserved, typ, value):
        self.keys[key.path][name] = value

    def DeleteValue(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        del self.keys[key.path][name]

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(name)
        return self.keys[key.path][name], REG_SZ

    def _children(self, path):
        depth = path.count("\\") + 1
        return sorted(
            k.split("\\")[-1] for k in self.keys
            if k.startswith(path + "\\") and k.count("\\") == depth
        )

    def EnumKey(self, key, index):
        kids = self._children(key.path)
        if index >= len(kids):
            raise OSError("No more data")
        return kids[index]

    def DeleteKey(self, hive, path):
        p = self._norm(path)
        if self._children(p):
            raise PermissionError("chave com subchaves não pode ser apagada")
        del self.keys[p]
