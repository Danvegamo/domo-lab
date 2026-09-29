<#
.SYNOPSIS
    Arma el nivel del abismo (Unreal genera el domo y lo manda por NDI) sin abrir la interfaz grafica.

.DESCRIPTION
    Corre crear_abismo.py con UnrealEditor-Cmd: materiales de /Game/Abismo y el nivel /Game/Maps/Abismo.
    Con el editor CERRADO y el modulo C++ compilado (UnrealBuildTool DomoVREditor, ver
    04_Docs\02_Sala_Unreal.md, seccion 8). Es idempotente.

    Log: 03_Unreal\Saved_Logs\crear_abismo.log
#>

$ErrorActionPreference = "Stop"

$Raiz = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal"
$Motor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64"
$UnrealEditorCmd = Join-Path $Motor "UnrealEditor-Cmd.exe"
$Proyecto = Join-Path $Raiz "DomoVR\DomoVR.uproject"
$Script = Join-Path $Raiz "crear_abismo.py"
$CarpetaLogs = Join-Path $Raiz "Saved_Logs"

foreach ($p in @($UnrealEditorCmd, $Proyecto, $Script)) {
    if (-not (Test-Path $p)) { Write-Error "No existe: $p"; exit 1 }
}
if (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue) {
    Write-Error "Hay un UnrealEditor abierto. Cerrarlo antes: dos procesos sobre el mismo proyecto se pisan el nivel."
    exit 1
}
New-Item -ItemType Directory -Path $CarpetaLogs -Force | Out-Null
$Log = Join-Path $CarpetaLogs "crear_abismo.log"
Write-Host "Corriendo crear_abismo.py headless (log: $Log)..."
& $UnrealEditorCmd $Proyecto -run=pythonscript "-script=$Script" -unattended -nosplash -nosound "-abslog=$Log" | Out-Null
$Codigo = $LASTEXITCODE
Write-Host "UnrealEditor-Cmd termino con codigo $Codigo"
Select-String -Path $Log -Pattern "\[crear_abismo\]|Error:" | ForEach-Object { $_.Line }
exit $Codigo
