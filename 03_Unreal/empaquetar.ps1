<#
.SYNOPSIS
    Empaqueta la sala standalone (Win64, Development) en 03_Unreal\Build\.

.DESCRIPTION
    Corre RunUAT BuildCookRun: compila el target de juego DomoVR, cocina los
    tres niveles (DomoVR, DomoVR_45, DomoVR_90) y /Game/Media, y deja el
    build con .pak en 03_Unreal\Build\Windows\. La carpeta Content\Movies\
    (videos y playlist.json) no entra al .pak: se copia suelta en
    Build\Windows\DomoVR\Content\Movies\ (DirectoriesToAlwaysStageAsNonUFS en
    Config\DefaultGame.ini). Al final comprueba que esten la playlist y los
    videos que nombra, y los copia si faltan.

    Correr con el editor CERRADO. La primera vez cocina todos los shaders y
    tarda (decenas de minutos); las siguientes, mucho menos.

    Para abrir el build:
        03_Unreal\Build\Windows\DomoVR.exe                        (sala 180)
        03_Unreal\Build\Windows\DomoVR.exe /Game/Maps/DomoVR_45   (sala 45)
    Sin visor de VR conectado conviene agregar -nohmd.

    Log: 03_Unreal\Saved_Logs\empaquetar.log

.PARAMETER Salida
    Carpeta del build (por defecto 03_Unreal\Build).
#>

param([string]$Salida = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\Build")

$ErrorActionPreference = "Stop"

$Raiz = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal"
$RunUAT = "C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat"
$Proyecto = Join-Path $Raiz "DomoVR\DomoVR.uproject"
$MoviesProyecto = Join-Path $Raiz "DomoVR\Content\Movies"
$CarpetaLogs = Join-Path $Raiz "Saved_Logs"
$Log = Join-Path $CarpetaLogs "empaquetar.log"

if (-not (Test-Path $RunUAT)) { Write-Error "No existe $RunUAT"; exit 1 }
if (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue) {
    Write-Error "Hay un UnrealEditor abierto. Cerrarlo antes de empaquetar."
    exit 1
}
if (-not (Test-Path (Join-Path $MoviesProyecto "playlist.json"))) {
    Write-Warning "No hay $MoviesProyecto\playlist.json: el build arrancara con la cupula en negro. Correr crear_media_domo.ps1."
}
New-Item -ItemType Directory -Path $CarpetaLogs -Force | Out-Null

$Mapas = "/Game/Maps/DomoVR+/Game/Maps/DomoVR_45+/Game/Maps/DomoVR_90"
$Argumentos = @(
    "BuildCookRun", "-project=`"$Proyecto`"", "-noP4", "-utf8output", "-unattended",
    "-platform=Win64", "-clientconfig=Development", "-target=DomoVR",
    "-build", "-cook", "-map=$Mapas", "-stage", "-pak", "-prereqs",
    "-archive", "-archivedirectory=`"$Salida`""
)
Write-Host "RunUAT BuildCookRun (log: $Log)..."
$Inicio = Get-Date
& $RunUAT @Argumentos 2>&1 | Tee-Object -FilePath $Log | Select-String -Pattern "BUILD SUCCESSFUL|BUILD FAILED|Error:|ExitCode=" | ForEach-Object { $_.Line }
$Codigo = $LASTEXITCODE
Write-Host ("RunUAT termino con codigo {0} en {1:N1} minutos" -f $Codigo, ((Get-Date) - $Inicio).TotalMinutes)
if ($Codigo -ne 0) { exit $Codigo }

# Comprobar (y si hace falta completar) la carpeta Movies del build.
$MoviesBuild = Join-Path $Salida "Windows\DomoVR\Content\Movies"
New-Item -ItemType Directory -Path $MoviesBuild -Force | Out-Null
$Playlist = Join-Path $MoviesProyecto "playlist.json"
if (Test-Path $Playlist) {
    if (-not (Test-Path (Join-Path $MoviesBuild "playlist.json"))) {
        Copy-Item $Playlist $MoviesBuild
        Write-Host "playlist.json copiada a mano (no la habia puesto el staging)."
    }
    $Datos = Get-Content $Playlist -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($Cue in $Datos.cues) {
        if ([System.IO.Path]::IsPathRooted($Cue.archivo)) {
            Write-Warning "El cue '$($Cue.nombre)' usa una ruta absoluta ($($Cue.archivo)): en otra maquina no va a existir."
            continue
        }
        $Destino = Join-Path $MoviesBuild $Cue.archivo
        if (-not (Test-Path $Destino)) {
            $Origen = Join-Path $MoviesProyecto $Cue.archivo
            if (Test-Path $Origen) {
                Copy-Item $Origen $Destino
                Write-Host "Copiado $($Cue.archivo)"
            } else {
                Write-Warning "Falta el video $($Cue.archivo) (ni en el proyecto ni en el build)."
            }
        }
    }
}
Write-Host "Build listo: $(Join-Path $Salida 'Windows\DomoVR.exe')"
exit 0
