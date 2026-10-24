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
Name: "bandeja"; Description: "Mostrar o Lotus ao lado do relógio (inicia com o Windows)"
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "..\dist\Lotus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lotus"; Filename: "{app}\Lotus.exe"
Name: "{group}\Desinstalar o Lotus"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lotus"; Filename: "{app}\Lotus.exe"; Tasks: desktopicon

[Run]
; Instalação nova: aplica as opções escolhidas. Atualização feita pelo próprio
; Lotus (/atualizacao=1): NÃO reaplica nada disso, para não desfazer o que a
; pessoa mudou depois no app; só refaz os caminhos e reabre o Lotus.
Filename: "{app}\Lotus.exe"; Parameters: "--instalar-menu --silencioso"; Tasks: menu; Check: InstalacaoNova; Flags: waituntilterminated; StatusMsg: "Instalando o menu do botão direito..."
Filename: "{app}\Lotus.exe"; Parameters: "--ativar-atalho --silencioso"; Tasks: atalho; Check: InstalacaoNova; Flags: waituntilterminated; StatusMsg: "Ligando o painel flutuante..."
Filename: "{app}\Lotus.exe"; Parameters: "--ativar-bandeja --silencioso"; Tasks: bandeja; Check: InstalacaoNova; Flags: waituntilterminated; StatusMsg: "Colocando o Lotus ao lado do relógio..."
Filename: "{app}\Lotus.exe"; Parameters: "--desativar-bandeja --silencioso"; Tasks: not bandeja; Check: InstalacaoNova; Flags: waituntilterminated
Filename: "{app}\Lotus.exe"; Parameters: "--pos-atualizacao --silencioso"; Check: Atualizacao; Flags: waituntilterminated
Filename: "{app}\Lotus.exe"; Check: Atualizacao; Flags: nowait
Filename: "{app}\Lotus.exe"; Description: "Abrir o Lotus agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove menu, início automático e para o agente. Os arquivos convertidos e a
; configuração do usuário (%APPDATA%\Lotus) não são apagados.
Filename: "{app}\Lotus.exe"; Parameters: "--desinstalar --silencioso"; Flags: waituntilterminated; RunOnceId: "LotusLimpeza"

[Code]
// /atualizacao=1 é passado pelo próprio Lotus (Ferramentas → Procurar atualização).
function Atualizacao: Boolean;
begin
  Result := ExpandConstant('{param:atualizacao|0}') = '1';
end;

function InstalacaoNova: Boolean;
begin
  Result := not Atualizacao;
end;
