<#
.SYNOPSIS
    Corre importar_sala.py (o conectar_spout.py) contra el proyecto DomoVR en
    modo headless, para el modelo de sala que se pida.

.DESCRIPTION
    Ejecuta UnrealEditor-Cmd.exe con -run=pythonscript para importar el FBX
    del modelo de sala y armar su nivel sin abrir la interfaz grafica. Rutas
    absolutas, corre desde cualquier directorio. Escribe un log en
    03_Unreal\Saved_Logs\<script>_<fov>.log (se crea la carpeta si no existe).

    -Fov 180 (por defecto): 02_Export\sala_domo.fbx -> /Game/Maps/DomoVR.
             Comportamiento original.
    -Fov 90 / -Fov 45: 02_Export\sala_domo_90.fbx -> /Game/Maps/DomoVR_90,
             mallas en /Game/Sala/Domo_90, materiales reutilizados. Ver
             04_Docs\05_Modelos_de_sala.md.
    -ScriptName conectar_spout.py: coloca el SpoutDomeReceiver en el nivel del
             modelo (correr despues de la importacion).

    Ejemplos:
        .\importar_sala.ps1
        .\importar_sala.ps1 -Fov 90
        .\importar_sala.ps1 -Fov 90 -ScriptName conectar_spout.py

    Si el FBX todavia no existe, el script de Python igual corre: salta la
    importacion de malla y arma el resto del nivel (ver importar_sala.py y
    04_Docs\Unreal_sala_domo.md).

    La primera corrida compila shaders y deriva datos; puede tardar varios
    minutos. No la interrumpas antes de que termine.

    OJO: es otro proceso de Unreal sobre el mismo .uproject. Con el editor
    grafico abierto solo es seguro para modelos cuyo nivel el editor NO tenga
    cargado (los casquetes); nunca reimportar el 180 con el editor abierto en
    /Game/Maps/DomoVR.
#>

param(
    [double]$Fov = 180,
    [string]$ScriptName = "importar_sala.py"
)

$ErrorActionPreference = "Stop"

$UnrealEditorCmd = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$Proyecto = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\DomoVR\DomoVR.uproject"
$Script = Join-Path "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal" $ScriptName
$CarpetaLogs = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\Saved_Logs"
$NombreLog = [System.IO.Path]::GetFileNameWithoutExtension($ScriptName) + "_" + $Fov + ".log"
$Log = Join-Path $CarpetaLogs $NombreLog

if (-not (Test-Path $UnrealEditorCmd)) {
    Write-Error "No se encontro UnrealEditor-Cmd.exe en: $UnrealEditorCmd"
    exit 1
}
if (-not (Test-Path $Proyecto)) {
    Write-Error "No se encontro el proyecto en: $Proyecto"
    exit 1
}
if (-not (Test-Path $Script)) {
    Write-Error "No se encontro el script en: $Script"
    exit 1
}
if (-not (Test-Path $CarpetaLogs)) {
    New-Item -ItemType Directory -Path $CarpetaLogs -Force | Out-Null
}

# Los dos scripts de Python leen el modelo de sala de esta variable.
$env:DOMO_FOV = "$Fov"

Write-Host "Corriendo $ScriptName de forma headless (modelo FOV $Fov)..."
Write-Host "  Editor:   $UnrealEditorCmd"
Write-Host "  Proyecto: $Proyecto"
Write-Host "  Script:   $Script"
Write-Host "  Log:      $Log"

# -abslog: ruta absoluta del log (con -log= Unreal la toma como nombre
# relativo a Saved\Logs y el archivo no aparecia en Saved_Logs).
& $UnrealEditorCmd $Proyecto -run=pythonscript "-script=$Script" -unattended -nosplash -nosound "-abslog=$Log"

$CodigoSalida = $LASTEXITCODE
Write-Host "UnrealEditor-Cmd.exe termino con codigo de salida: $CodigoSalida"
exit $CodigoSalida
