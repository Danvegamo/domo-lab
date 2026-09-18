<#
.SYNOPSIS
    Arma la version standalone (video en la cupula sin TouchDesigner) en los
    tres niveles de la sala, sin abrir la interfaz grafica.

.DESCRIPTION
    1. Genera los videos de prueba (el patron en 360, domemaster y VR180) en
       03_Unreal\DomoVR\Content\Movies\ si no existen (necesita Python con
       Pillow y ffmpeg; si faltan, avisa y sigue).
    2. Corre crear_media_domo.py con UnrealEditor-Cmd -run=pythonscript:
       MP_Domo, MT_Domo, M_DomoMedia, MI_DomoMedia y un DomeMediaController
       en DomoVR, DomoVR_45 y DomoVR_90.
    3. Con -SoloRC, arma el preset de Remote Control RC_Domo. Eso no se puede
       en modo commandlet (exponer una funcion necesita el buffer de
       transacciones del editor y el proceso se cae), asi que abre el editor
       completo con -ExecutePythonScript, sin render en pantalla
       (-RenderOffscreen), y lo cierra al terminar.

    Correr con el editor CERRADO y despues de importar_sala.ps1 y
    conectar_spout (para cada modelo), porque reimportar un nivel lo vacia y
    se lleva el controlador. El modulo C++ tiene que estar compilado
    (UnrealBuildTool DomoVREditor, ver 04_Docs\02_Sala_Unreal.md, seccion 8).

    Log: 03_Unreal\Saved_Logs\crear_media_domo.log (o crear_media_domo_rc.log)

    Ejemplos:
        .\crear_media_domo.ps1
        .\crear_media_domo.ps1 -SoloRC
#>

param([switch]$SoloRC)

$ErrorActionPreference = "Stop"

$Raiz = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal"
$Motor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64"
$UnrealEditorCmd = Join-Path $Motor "UnrealEditor-Cmd.exe"
$UnrealEditor = Join-Path $Motor "UnrealEditor.exe"
$Proyecto = Join-Path $Raiz "DomoVR\DomoVR.uproject"
$Script = Join-Path $Raiz "crear_media_domo.py"
$CarpetaLogs = Join-Path $Raiz "Saved_Logs"
$CarpetaMovies = Join-Path $Raiz "DomoVR\Content\Movies"

foreach ($p in @($UnrealEditorCmd, $Proyecto, $Script)) {
    if (-not (Test-Path $p)) { Write-Error "No existe: $p"; exit 1 }
}
if (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue) {
    Write-Error "Hay un UnrealEditor abierto. Cerrarlo antes: dos procesos sobre el mismo proyecto se pisan el nivel."
    exit 1
}
New-Item -ItemType Directory -Path $CarpetaLogs -Force | Out-Null

if ($SoloRC) {
    $Log = Join-Path $CarpetaLogs "crear_media_domo_rc.log"
    $env:DOMO_SOLO_RC = "1"
    $env:DOMO_SALIR = "1"
    Remove-Item Env:DOMO_HEADLESS -ErrorAction SilentlyContinue
    Write-Host "Armando RC_Domo con el editor completo, sin ventana (log: $Log)..."
    $Argumentos = @("`"$Proyecto`"", "-ExecutePythonScript=`"$Script`"", "-RenderOffscreen",
                    "-unattended", "-nosplash", "-nosound", "-abslog=`"$Log`"")
    $Proceso = Start-Process -FilePath $UnrealEditor -ArgumentList $Argumentos -PassThru -Wait
    Write-Host "UnrealEditor termino con codigo $($Proceso.ExitCode)"
    Select-String -Path $Log -Pattern "\[crear_media_domo\]" | ForEach-Object { $_.Line }
    exit $Proceso.ExitCode
}

foreach ($Formato in @("360", "domemaster", "vr180")) {
    $Nombre = if ($Formato -eq "360") { "patron_4096x2048.mp4" } else { "patron_$($Formato)_2048.mp4" }
    $Destino = Join-Path $CarpetaMovies $Nombre
    if (Test-Path $Destino) { continue }
    Write-Host "Generando el video de prueba $Nombre..."
    try {
        & python (Join-Path $Raiz "generar_video_patron.py") $Destino --formato $Formato
    } catch {
        Write-Warning "No se pudo generar $Nombre ($_). Sigue sin el; se puede correr generar_video_patron.py despues."
    }
}

$Log = Join-Path $CarpetaLogs "crear_media_domo.log"
$env:DOMO_HEADLESS = "1"
Remove-Item Env:DOMO_SOLO_RC -ErrorAction SilentlyContinue
Write-Host "Corriendo crear_media_domo.py headless (log: $Log)..."
& $UnrealEditorCmd $Proyecto -run=pythonscript "-script=$Script" -unattended -nosplash -nosound "-abslog=$Log"
$Codigo = $LASTEXITCODE
Write-Host "UnrealEditor-Cmd termino con codigo $Codigo"
Select-String -Path $Log -Pattern "\[crear_media_domo\]|Error:" | ForEach-Object { $_.Line }
exit $Codigo
