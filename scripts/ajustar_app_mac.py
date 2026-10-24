"""Completa o Info.plist do Lotus.app gerado pelo PyInstaller (macOS).

- NSAppleEventsUsageDescription: sem ele o macOS nega, sem perguntar, o
  acesso ao Finder (ler a seleção para o painel flutuante).
- Versão do app.
Uso: python scripts/ajustar_app_mac.py dist/Lotus.app 0.6.0
Depois: codesign --force --deep --sign - dist/Lotus.app (assinatura local).
"""

import plistlib
import sys
from pathlib import Path

app, versao = Path(sys.argv[1]), sys.argv[2]
arq = app / "Contents" / "Info.plist"
info = plistlib.loads(arq.read_bytes())
info.update({
    "CFBundleName": "Lotus",
    "CFBundleDisplayName": "Lotus",
    "CFBundleShortVersionString": versao,
    "CFBundleVersion": versao,
    "NSHighResolutionCapable": True,
    "NSAppleEventsUsageDescription": (
        "O Lotus pergunta ao Finder quais arquivos estão selecionados para mostrar "
        "o painel de conversão. Nada sai do seu Mac."
    ),
})
arq.write_bytes(plistlib.dumps(info))
print(f"Info.plist ajustado: {arq}")
