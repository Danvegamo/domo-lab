<#
.SYNOPSIS
    Corre importar_sala.py contra el proyecto DomoVR en modo headless.

.DESCRIPTION
    Ejecuta UnrealEditor-Cmd.exe con -run=pythonscript para importar
    sala_domo.fbx (02_Export\sala_domo.fbx) y armar el nivel /Game/Maps/DomoVR
    sin abrir la interfaz grafica. Rutas absolutas, corre desde cualquier
    directorio. Escribe ademas un log en 03_Unreal\Saved_Logs\importar_sala.log
    (se crea la carpeta si no existe).

    Si sala_domo.fbx todavia no existe, el script de Python igual corre:
    salta la importacion de malla y arma el resto del nivel (ver
    importar_sala.py y 04_Docs\Unreal_sala_domo.md).

    La primera corrida compila shaders y deriva datos; puede tardar varios
    minutos. No la interrumpas antes de que termine.
#>

$ErrorActionPreference = "Stop"

$UnrealEditorCmd = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$Proyecto = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\DomoVR\DomoVR.uproject"
$Script = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\importar_sala.py"
$CarpetaLogs = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\Saved_Logs"
$Log = Join-Path $CarpetaLogs "importar_sala.log"

if (-not (Test-Path $UnrealEditorCmd)) {
    Write-Error "No se encontro UnrealEditor-Cmd.exe en: $UnrealEditorCmd"
    exit 1
}
if (-not (Test-Path $Proyecto)) {
    Write-Error "No se encontro el proyecto en: $Proyecto"
    exit 1
}
if (-not (Test-Path $Script)) {
    Write-Error "No se encontro el script de importacion en: $Script"
    exit 1
}
if (-not (Test-Path $CarpetaLogs)) {
    New-Item -ItemType Directory -Path $CarpetaLogs -Force | Out-Null
}

Write-Host "Corriendo importar_sala.py de forma headless..."
Write-Host "  Editor:   $UnrealEditorCmd"
Write-Host "  Proyecto: $Proyecto"
Write-Host "  Script:   $Script"
Write-Host "  Log:      $Log"

& $UnrealEditorCmd $Proyecto -run=pythonscript "-script=$Script" -unattended -nosplash -nosound "-log=$Log"

$CodigoSalida = $LASTEXITCODE
Write-Host "UnrealEditor-Cmd.exe termino con codigo de salida: $CodigoSalida"
exit $CodigoSalida
