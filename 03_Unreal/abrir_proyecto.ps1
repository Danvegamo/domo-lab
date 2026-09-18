<#
.SYNOPSIS
    Abre el proyecto DomoVR en el editor grafico de Unreal Engine 5.8.

.DESCRIPTION
    Lanza UnrealEditor.exe (interfaz completa) contra DomoVR.uproject.
    Usa rutas absolutas: se puede correr desde cualquier directorio.
    La primera apertura compila shaders y deriva datos; puede tardar varios
    minutos con la GPU al 100%. Eso es normal, no es que se haya colgado.
#>

$ErrorActionPreference = "Stop"

$UnrealEditor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$Proyecto = "C:\Users\Danvegamo\Documents\Domo_VR_Unreal\03_Unreal\DomoVR\DomoVR.uproject"

if (-not (Test-Path $UnrealEditor)) {
    Write-Error "No se encontro UnrealEditor.exe en: $UnrealEditor"
    exit 1
}
if (-not (Test-Path $Proyecto)) {
    Write-Error "No se encontro el proyecto en: $Proyecto"
    exit 1
}

Write-Host "Abriendo DomoVR en el editor de Unreal 5.8..."
Write-Host "  Editor:   $UnrealEditor"
Write-Host "  Proyecto: $Proyecto"

# -culture=en fuerza la interfaz del editor en ingles, aunque Windows este en espanol.
& $UnrealEditor $Proyecto -culture=en
