; Instalador do Lotus (Inno Setup 6). Gerado no CI: veja .github/workflows/ci.yml.
; Compilar à mão:  ISCC /DAppVersion=0.3.0 installer\lotus.iss
; Espera o programa empacotado em dist\Lotus (PyInstaller --onedir).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId identifica o programa para atualizações/desinstalação: NUNCA mude.
AppId={{6F1D2B7A-3C4E-4A8B-9E21-7D5C0B3A9F41}
AppName=Lotus
AppVersion={#AppVersion}
AppVerName=Lotus {#AppVersion}
AppPublisher=Kiuwar
DefaultDirName={autopf}\Lotus
DefaultGroupName=Lotus
DisableProgramGroupPage=yes
; Por usuário: não pede administrador; instala em %LOCALAPPDATA%\Programs\Lotus.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=LotusSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Lotus.exe
; Flor de lótus (gerada por scripts/gerar_icone.py).
SetupIconFile=..\conversor\recursos\lotus.ico
UninstallDisplayName=Lotus
; Fecha o Lotus (inclusive o painel em segundo plano) antes de atualizar/remover.
CloseApplications=force

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "menu"; Description: "Adicionar ""Converter para"" ao botão direito do mouse"
Name: "atalho"; Description: "Ligar o painel flutuante (Ctrl+Shift+clique num arquivo do Explorer)"
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "..\dist\Lotus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lotus"; Filename: "{app}\Lotus.exe"
Name: "{group}\Desinstalar o Lotus"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lotus"; Filename: "{app}\Lotus.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lotus.exe"; Parameters: "--instalar-menu --silencioso"; Tasks: menu; Flags: waituntilterminated; StatusMsg: "Instalando o menu do botão direito..."
Filename: "{app}\Lotus.exe"; Parameters: "--ativar-atalho --silencioso"; Tasks: atalho; Flags: waituntilterminated; StatusMsg: "Ligando o painel flutuante..."
Filename: "{app}\Lotus.exe"; Description: "Abrir o Lotus agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove menu, início automático e para o agente. Os arquivos convertidos e a
; configuração do usuário (%APPDATA%\Lotus) não são apagados.
Filename: "{app}\Lotus.exe"; Parameters: "--desinstalar --silencioso"; Flags: waituntilterminated; RunOnceId: "LotusLimpeza"
