# El ejecutable en tarjetas AMD e Intel

`DomoVR.exe` se desarrolló y se probó en una sola tarjeta, una NVIDIA RTX 3090.
Esta página decide qué sistema usa el ejecutable cuando la tarjeta es AMD o
Intel, con qué evidencia, y deja escrito lo que solo se puede confirmar con la
tarjeta en la mano (sección 9). Complementa a
[06_Unreal_standalone.md](06_Unreal_standalone.md) (video y ejecutable) y a
[02_Sala_Unreal.md](02_Sala_Unreal.md) (render, secciones 11 y 14).

Todo lo que dice «motor» se leyó en el código de Unreal Engine 5.8 instalado en
`C:\Program Files\Epic Games\UE_5.8\Engine`; las rutas se citan relativas a esa
carpeta. Lo que dice «medido» se corrió el 29 de septiembre de 2026 con el
build empaquetado, en la RTX 3090, y es la única medición real de esta página.

## 1. Resumen y decisión

| Tema | Decisión |
|---|---|
| Sistema de video que vale para todos | **H.264 de 8 bits, 4:2:0, hasta 4096 × 2304 y 120 cuadros por segundo** (recomendado: 2048 de lado para lo pesado). Lo abre Electra con el decodificador de Media Foundation de Windows, que usa la GPU de cualquier fabricante y no necesita ninguna extensión de códec. |
| HEVC pesado (4096 × 4096 nivel 6.0) en AMD e Intel | Solo lo abre por GPU el **decodificador D3D12 Video de Electra**, y viene **apagado de fábrica** (sección 3.3). Hay que encenderlo con `ElectraDecoders.bDoNotUseD3D12Video 0`. Medido en la RTX 3090: **sí abre HEVC 4096 × 4096 nivel 6.0**. En AMD e Intel no está verificado. |
| Si no se enciende o falla | Cadena de respaldo: decodificador D3D12 (si se encendió) → decodificador Media Foundation de Electra (HEVC hasta nivel 5.2 y 4096 × 2304) → `WmfMedia` en CPU. Para archivos que solo caben en CPU: **Optimizar video** con el codificador de cada fabricante (sección 4). |
| Codificador de ffmpeg | NVIDIA `h264_nvenc`, AMD `h264_amf`, Intel `h264_qsv`, y `libx264` como último respaldo. Decodificar con `-hwaccel cuda`, `d3d11va` y `qsv` respectivamente. |
| Render | Tres perfiles: **Alta** (RTX o AMD RDNA2 o más nuevo, con VRAM de sobra), **Media** (Lumen; con trazado por hardware si hay DXR 1.1 y 8 GB, si no por software), **Baja** (iGPU o menos de 4 GB, sin trazado por hardware). Ver la sección 5. |
| Escalador | Quedarse con **TSR**, que viene en el motor y es igual en los tres fabricantes. FSR y XeSS son plugins de terceros; DLSS también. Ninguno viene en UE 5.8 (solo el plugin `Reflex` de NVIDIA). |
| Detección | `IsRHIDeviceNVIDIA/AMD/Intel()`, `GRHIVendorId`, `GRHIAdapterName`, `GRHIGlobals.GpuInfo.DedicatedVideoMemory` y `GRHISupportsRayTracing` (sección 6). El controlador ya usa varios en `DescribirPerfil` y `ElegirPerfilAuto`. |

## 2. Hallazgo que cambia el código

El plugin `D3D12VideoDecodersElectra` se habilitó en `DomoVR.uproject` con la
idea de que cubre H.264 y HEVC en cualquier fabricante. En el motor, esa
decodificación está **apagada por defecto en Windows**:

- `Plugins/Media/D3D12VideoDecodersElectra/Source/D3D12VideoDecodersElectra.Build.cs:14-19`:
  `bIsDefaultIgnoredOnPlatform` devuelve `true`, y la línea 25 lo pasa como
  `ELECTRA_DECODERS_D3D12VIDEO_IGNORED_ON_PLATFORM=1`.
- `.../Source/Private/VideoDecoder_D3D12.cpp:40-44` y `:52-55`: con ese
  símbolo, la variable `ElectraDecoders.bDoNotUseD3D12Video` arranca en `true`.
- `.../VideoDecoder_D3D12.cpp:455` y `:472`: con la variable en `true`,
  `SupportsDecoding` devuelve 0 siempre, o sea que la fábrica se registra
  pero nunca se elige.

Consecuencias, ya medidas en la 3090 (tres corridas del mismo guion con
cuatro clips, sección 8):

| Corrida | Variables | Qué decodificó | Resultado |
|---|---|---|---|
| A, tal como sale hoy | de fábrica | **NVDEC** en los cuatro clips (`Created an NVDEC decoder`) | los cuatro abren con `ElectraPlayer` |
| B | `bDoNotUseD3D12Video 0` y `bDisableNVDEC 1` | **D3D12 Video** en los cuatro (`Created a D3D12 video decoder`) | los cuatro abren con `ElectraPlayer`, **incluido HEVC 4096 × 4096 nivel 6.0** |
| C | las dos apagadas | decodificador de Media Foundation de Electra en tres clips (deducido: es la única fábrica que queda; el log no lo nombra); `WmfMedia` (CPU) en el HEVC nivel 6.0 | el aviso «Video pesado (4096x4096) decodificado en CPU» sale solo en el HEVC de nivel 6.0 |

Es decir:

1. La afirmación de `06_Unreal_standalone.md` (sección 5) de que el
   decodificador de D3D12 «no acepta HEVC nivel 6» **no se sostiene**. El
   código lo acepta hasta el nivel 6.3 (`VideoDecoder_D3D12.cpp:375`,
   `Level > 189`) y en la 3090 lo abrió. En el ejecutable de hoy simplemente
   nunca se probó, porque NVDEC (prioridad 100) le gana y el de D3D12 está
   apagado.
2. En AMD e Intel el ejecutable, tal como está, **no** decodifica HEVC de
   4096 × 4096 por GPU: NVDEC no existe, D3D12 está apagado y el decodificador
   de Media Foundation lo rechaza por nivel y por tamaño (sección 3.5). Cae a
   `WmfMedia` (CPU), exactamente el caso que el 29 de septiembre de 2026
   llevaba a 6,5 núcleos y a un video que se traba.
3. La corrección mínima es encender esa variable cuando la tarjeta no es
   NVIDIA. Es la decisión central de este documento. La lista de cambios está
   en la sección 10.

## 3. Decodificación de video

### 3.1 Quién decodifica y en qué orden

Electra pregunta a todas las fábricas registradas y se queda con la que
devuelve el número más alto (`Plugins/Media/ElectraCodecs/Source/ElectraCodecFactory/Private/ElectraCodecFactoryModule.cpp:103-110`).

| Decodificador | Prioridad | Requisitos | Códecs | Dónde se ve |
|---|---|---|---|---|
| NVDEC (`NVDECElectra`) | 100 | NVIDIA, driver 531.61 o más nuevo, CUDA | H.264, HEVC, AV1, VP9, VP8 (según la tarjeta) | `NVDECElectra/.../ElectraMediaNVDEC.cpp:776`, `:832-845` |
| D3D12 Video (`D3D12VideoDecodersElectra`) | 5 | cualquier fabricante con `ID3D12VideoDevice` y decode tier 2; **apagado de fábrica** | H.264 y HEVC | `VideoDecoder_D3D12.cpp:467`, `:455` |
| Media Foundation de Electra (`ElectraCodecs`) | 1 | Windows con el decodificador MF del códec; para HEVC hace falta la extensión de Windows (sección 3.5) | H.264 y HEVC | `ElectraDecoders/Private/Windows/h265/H265_VideoDecoder_Windows.cpp:87` |
| `WmfMedia` | fuera de Electra | Windows; con DX12 decodifica en CPU | lo que instale Windows | `06_Unreal_standalone.md`, sección 5 |

`ElectraPlayer` decide por archivo. Si ninguna fábrica lo acepta, el
reproductor falla al abrir, y `ADomeMediaController::AlFallarApertura`
(`DomeMediaController.cpp:1509-1530`) reabre el cue con `WmfMedia`.

### 3.2 Qué acepta el decodificador D3D12 (código)

Todo sale de `GetFormatIfSupported` (`VideoDecoder_D3D12.cpp:333-450`) y de la
búsqueda de perfiles (`:56-200`):

| Punto | Lo que hace el código | Línea |
|---|---|---|
| Perfiles que pide al driver | H.264, HEVC Main, HEVC Main10, VP9 y VP9 10 bits; solo se usan formatos de salida NV12, P010 o P016 | `:119-160`, `:187-200` |
| H.264 | Solo perfiles 66 (Baseline), 77 (Main) y 100 (High), 8 bits. No mira el nivel: lo decide el driver | `:365` |
| HEVC | Solo Main (1) y Main10 (2), espacio de perfil 0, **nivel ≤ 189** (6.3: límite de tiles de la estructura DXVA `DXVA_PicParams_HEVC`) | `:375-395` |
| VP9 y AV1 | No hay decodificador: `GetFormatIfSupported` devuelve nulo y `CreateDecoder` solo crea H.264 y H.265 | `:403`, `:535-548` |
| Tamaño, cuadros y bitrate | Los manda tal cual a `CheckFeatureSupport(D3D12_FEATURE_VIDEO_DECODE_SUPPORT)`; el tope real lo pone el driver | `:413-420` |
| Decode tier 2 | Exige `D3D12_VIDEO_DECODE_TIER_2`. Con tier 1 se descarta. Microsoft: el tier 1 obliga a un arreglo de texturas; el 2 permite texturas 2D sueltas, que es lo que el código asigna (una por cuadro del DPB, `:960-985`) | `:424-428` |
| Reference-only | Si el driver marca `D3D12_VIDEO_DECODE_CONFIGURATION_FLAG_REFERENCE_ONLY_ALLOCATIONS_REQUIRED`, se descarta. El código crea el DPB con `D3D12_RESOURCE_FLAG_NONE` (`:971`) y no sabe hacerlo de otra forma | `:431-435` |
| Alineación | H.264 alinea ancho y alto a 16 (`VideoDecoder_D3D12_H264.cpp:240`); HEVC a 64 para el DPB (`VideoDecoder_D3D12_H265.h:74`) y al tamaño mínimo de CB para el heap (`VideoDecoder_D3D12_H265.cpp:277`) | |
| Banderas que ignora | `HEIGHT_ALIGNMENT_MULTIPLE_32_REQUIRED`, `POST_PROCESSING_SUPPORTED` y `ALLOW_RESOLUTION_CHANGE_ON_NON_KEY_FRAME` no aparecen en ningún archivo del plugin | (búsqueda) |
| Adaptador | Usa el dispositivo del RHI (`RHIGetDevice_NoMGPU`) y el nodo 0; no cruza tarjetas | `:70-96` |
| Vendor | No hay ninguna comprobación de fabricante | — |

Sobre las banderas ignoradas: un driver que exija alto múltiplo de 32 fallaría
con un alto de 720 alineado a 16 (720 no es múltiplo de 32). Los tamaños que
usa el proyecto (2048 × 2048, 4096 × 2048, 4096 × 4096) son múltiplos de 32 y
no se ven afectados.

Microsoft documenta el tier, las banderas y la asignación de referencias en
[D3D12_VIDEO_DECODE_TIER](https://learn.microsoft.com/en-us/windows/win32/api/d3d12video/ne-d3d12video-d3d12_video_decode_tier)
y [D3D12_VIDEO_DECODE_CONFIGURATION_FLAGS](https://learn.microsoft.com/en-us/windows/win32/api/d3d12video/ne-d3d12video-d3d12_video_decode_configuration_flags).
Qué tier y qué banderas informa cada driver de AMD e Intel **no se pudo
confirmar** sin la tarjeta (sección 9). La 3090 no imprimió ninguno de los
avisos `Decode tier 2 is needed` ni `reference only allocations`
(`VideoDecoder_D3D12.cpp:426`, `:433`), así que informa tier 2 sin la bandera.

### 3.3 Cómo encender el decodificador D3D12

La variable se lee cada vez que Electra elige decodificador
(`VideoDecoder_D3D12.cpp:455`, `:472`), así que se puede cambiar en cualquier
momento antes de abrir el cue. Se probó por consola, con el juego corriendo, y
por guion: `ElectraDecoders.bDoNotUseD3D12Video 0` y luego `domo.Cue 1`
(que reabre el video) usó el decodificador D3D12 (corrida B). En C++:

```cpp
if (IConsoleVariable* V = IConsoleManager::Get().FindConsoleVariable(
        TEXT("ElectraDecoders.bDoNotUseD3D12Video")))
{
    V->Set(0, ECVF_SetByConsole);
}
```

Ponerla en `DefaultEngine.ini` (`[SystemSettings]`) es la opción más limpia,
pero **no se probó** que se aplique antes de que la fábrica consulte la
variable; hacerlo desde el controlador antes del primer `OpenSource` sí está
probado por el equivalente de consola. `ElectraDecoders.bDisableD3D12Video`
(`:46-49`) es otra variable distinta: solo se lee en `Startup()` (`:1052-1054`) y
por defecto está en falso, no hay que tocarla.

### 3.4 Qué dice el hardware de AMD e Intel

Los tamaños son de fuentes de los fabricantes o de terceros, no del código de
Epic. El decodificador D3D12 los ve a través del driver, así que el número
final puede ser menor.

| Familia | HEVC Main / Main10 | H.264 | AV1 | VP9 | Fuente |
|---|---|---|---|---|---|
| AMD RDNA2 (VCN 3.0: RX 6800, 6700, 6600) | hasta 7680 × 4320, 8 y 10 bits | hasta 4096 × 2176 | 8192 × 4352 | 7680 × 4320 | rocDecode, tabla VCN 3.x |
| AMD RDNA2 pequeña (Navi 24: RX 6400, 6500 XT) | sí | sí | **no** | sí | Wikipedia, «Video Core Next» |
| AMD RDNA3 (VCN 4.0: RX 7000) | hasta 7680 × 4320 | hasta 4096 × 2176 | 8192 × 4352 | 7680 × 4320 | rocDecode, tabla VCN 4.0 |
| AMD RDNA4 (VCN 5.0: RX 9000) | no hay cifra publicada en las fuentes revisadas | idem | idem | idem | Wikipedia; sin tabla de tamaños |
| AMD RDNA1 y APU anteriores (VCN 1.0 y 2.x) | «4K»; sin cifra exacta | sí | no | sí | Wikipedia |
| Intel Arc A y B, iGPU Xe (Gen 11 a 13) | **16K** (16384), 8 y 10 bits, más 4:2:2 y 4:4:4 | «4K» | 8 y 10 bits (Arc; iGPU según generación) | sí | Intel, «Features and Formats»; «Video Codecs Supported by Intel Arc GPUs» |
| Intel UHD anterior (Gen 9 y 10) | 8K | 4K | no | parcial | Intel, «Features and Formats» |

Lo que sigue para el proyecto:

- **HEVC 4096 × 4096 nivel 6.0 a 30 cuadros** (503 megapíxeles por segundo)
  cabe con holgura en RDNA2 o más nuevo y en Arc, por tamaño y por caudal. Es
  el mismo cálculo que en NVIDIA; falta que el driver de cada fabricante lo
  acepte por D3D12 (sección 9).
- **HEVC 4096 × 2048 a 60 cuadros** es nivel 5.1 (534,8 megapíxeles por
  segundo de tope; el clip hace 503) y lo cubre incluso el decodificador de
  Media Foundation.
- **H.264 de AMD llega a 4096 × 2176**, o sea que un H.264 de 4096 × 2304,
  que el decodificador de Media Foundation de Electra declara aceptable,
  puede no abrirse por GPU en AMD. Por eso el H.264 recomendado es de 2048 de
  lado: cabe en todos.
- **AV1 y VP9 solo por NVDEC.** En AMD e Intel, Electra no tiene decodificador
  de GPU para ellos y el proyecto no habilita los plugins de software
  (`AV1DecoderElectra`, `VPxDecoderElectra`). No usar AV1 ni VP9 en estas
  tarjetas.
- 4:2:2, 4:4:4 y 10 bits en H.264 se rechazan en los tres caminos (solo
  perfiles 66, 77 y 100 en H.264; solo Main y Main10 en HEVC).

### 3.5 Si D3D12 Video no lo acepta: el decodificador de Media Foundation de Electra

Es el respaldo de Electra (prioridad 1) y el que quedaría activo en AMD e
Intel con el D3D12 apagado. Vive en `ElectraCodecs/Source/ElectraDecoders/Private/Windows`:

| Códec | Perfiles | Nivel máximo | Tamaño máximo | Cuadros | Línea |
|---|---|---|---|---|---|
| H.264 | 66, 77, 100 | 5.2 (`52`) | 4096 × 2304 | 120 | `h264/H264_VideoDecoder_Windows.cpp:190-194` |
| HEVC | Main (1), Main10 (2) | 5.2 (`156`) | 4096 × 2304 | 120 | `h265/H265_VideoDecoder_Windows.cpp:177-179` |

La comparación de tamaños no depende de la orientación: compara lado largo
contra lado largo y corto contra corto (`ElectraDecodersUtils.h:59-66`), así
que 2304 × 4096 se trata igual que 4096 × 2304. Un 4096 × 4096 **siempre** lo
excede, y HEVC de nivel 6.0 (`180`) supera el 156.

Cómo funciona: crea el decodificador de Media Foundation del sistema y, si es
«D3D11 aware», le asocia el dispositivo de la GPU
(`H265_VideoDecoder_Windows.cpp:245-355`). Con DX12 usa el propio dispositivo
DX12 si el SDK de Windows es 22621 o más (`WindowsPlatformHeaders_Video_DX.h:23`)
y si no crea uno de D3D11 en el mismo adaptador. **Si no puede asociar el
dispositivo, cae a decodificación por software** dentro de Electra
(`bIsSW = true`, líneas 358 y 370): el archivo abre pero en CPU, y
no hay aviso en pantalla porque el reproductor sigue siendo `ElectraPlayer`.
Para H.264 hay además `Electra.Win.UseSoftwareDecodingH264` (por defecto 0).

Dos consecuencias para AMD e Intel:

1. **HEVC en Windows necesita la extensión.** El decodificador HEVC de Media
   Foundation no viene en Windows 10 ni 11 sin más; se instala con «HEVC
   Video Extensions» (de la Tienda, de pago, o la versión «del fabricante del
   equipo»). Sin ella fallan el decodificador de Media Foundation de Electra
   y también `WmfMedia`, y el HEVC solo podría abrirse por D3D12 Video o por
   NVDEC. Es una razón más para encender D3D12 en AMD e Intel. Fuente:
   [documentación de Microsoft sobre el decodificador H.265](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/medfound/h-265---hevc-video-decoder.md)
   y las preguntas sobre la extensión en Microsoft Q&A. En la 3090 de Dan el
   respaldo `WmfMedia` sí abrió HEVC (corrida C), así que ahí la extensión
   está instalada.
2. **H.264 no necesita nada extra**: el decodificador H.264 viene con
   Windows. Por eso H.264 es el formato seguro.

### 3.6 NVDECElectra sin NVIDIA: se desactiva solo

No hace falta tocar `DomoVR.uproject`. En el arranque, el módulo hace esto:

- `NVDECElectraModule.cpp:25-50`: si la aplicación puede renderizar y el RHI
  es D3D12, llama a `FElectraMediaNVDECDecoder::Startup()`; si no, lo deja.
- `ElectraMediaNVDEC.cpp:832-836`: `if (!IsRHIDeviceNVIDIA())` escribe
  `RHI device is not from NVIDIA, cannot use NVDEC acceleration.` y vuelve, sin
  cargar CUDA ni `nvcuvid.dll` (la carga es posterior, `:845`) y sin registrar
  la fábrica.
- Con NVIDIA pero sin CUDA o con un driver anterior a 531.61, se apaga con
  otro mensaje (`:840-844`, `:877`).

Medido en esta máquina forzando el adaptador «Microsoft Basic Render Driver»
(`-graphicsadapter=1 -AllowSoftwareRendering`, identificador de fabricante
distinto de NVIDIA): salió exactamente esa línea de `LogNVDECElectraDecoder`,
y `LogD3D12VideoDecodersElectra` escribió `The current RHI device is not a
video decoding capable device` y `D3D12 video decoding will not be used since
no supported format was found`. Ese adaptador no sirve para nada más: el juego
se cayó después por compilación de shaders. No es una prueba en AMD ni en
Intel; solo confirma que el módulo de NVDEC no estorba con otro fabricante.

### 3.7 Qué pasa con cada video, por fabricante

«Hoy» es el ejecutable tal como está; «con D3D12 encendido» es la propuesta de
la sección 10. Los renglones de NVIDIA son los medidos; los de AMD e Intel son
lo que el código y las fuentes de la sección 3.4 indican, **no verificados**.

| Video | NVIDIA (RTX 3090) | AMD o Intel, hoy | AMD o Intel con D3D12 encendido |
|---|---|---|---|
| H.264 4096 × 2048 a 60, nivel 5.2 | NVDEC. Medido | Media Foundation de Electra (GPU vía DXVA) | D3D12 Video |
| H.264 2048 de lado (copia de Optimizar) | NVDEC | Media Foundation de Electra | D3D12 Video |
| HEVC Main 4096 × 2048 a 60, nivel 5.1 | NVDEC. Medido | Media Foundation de Electra; exige la extensión HEVC | D3D12 Video |
| HEVC Main10 4096 × 2048 a 60 | NVDEC. Medido | Media Foundation de Electra; la textura del proyecto es de 8 bits | D3D12 Video |
| HEVC Main 4096 × 4096 nivel 6.0 (video de Dan) | NVDEC. Medido; también D3D12 Video (corrida B) | **`WmfMedia` en CPU** con aviso de «video pesado» | D3D12 Video si el driver lo acepta; si no, `WmfMedia` |
| AV1, VP9 | NVDEC | no abre por GPU | no abre por GPU |
| HEVC 4:4:4, ProRes, MPEG-4 parte 2 | `WmfMedia` o nada | `WmfMedia` o nada | `WmfMedia` o nada |

## 4. Videos muy pesados: transcodificar con ffmpeg por fabricante

**Optimizar video** (`ADomeMediaController::LanzarFfmpeg`,
`DomeMediaController.cpp:1912-1940`) hoy solo sabe NVIDIA: la fase 0 usa
`-hwaccel cuda` con `scale_cuda` y `h264_nvenc`, la fase 1 decodifica en CPU y
codifica con NVENC, y la fase 2 usa `libx264`. En AMD e Intel las fases 0 y 1
fallan siempre (no hay CUDA ni NVENC) y solo la 2 funciona, tras dos intentos
inútiles y lentos. La propuesta es elegir la cadena de fases por fabricante y
dar a cada uno su codificador de GPU antes de caer a `libx264`.

El ffmpeg que hay en esta máquina (gyan.dev 9.0.2 «essentials») ya trae los
tres codificadores (`--enable-amf`, `--enable-libvpl`, `--enable-nvenc`) y los
aceleradores de decodificación `cuda`, `d3d11va`, `dxva2`, `qsv`, `d3d12va` y
`amf`. Un ffmpeg incluido junto al ejecutable tiene que traerlos; en un equipo
AMD el codificador además necesita `amfrt64.dll` (viene con el driver) y en
Intel el runtime oneVPL del driver.

### 4.1 Cadena por fabricante

Sea `L` el lado destino (2048 por defecto, `LadoOptimizado`), `W×H` el tamaño
de salida que calcula el controlador (encajado en `L × L`, con ancho y alto
pares) y `ENT` y `SAL` los archivos. Se pasan `W` y `H` explícitos a todos los
filtros; así se evitan las diferencias de opciones entre `scale`, `scale_cuda`
y `vpp_qsv` (`vpp_qsv` no tiene `force_original_aspect_ratio`).

| Fabricante | Fase 0: decodifica y codifica por GPU | Fase 1: decodifica sin GPU, codifica por GPU | Fase 2 |
|---|---|---|---|
| NVIDIA | igual que hoy | igual que hoy | `libx264` |
| AMD | decodificación `d3d11va` + codificador `h264_amf` | decodificación por CPU + `h264_amf` | `libx264` |
| Intel | decodificación y filtro `qsv` + `h264_qsv` | decodificación `d3d11va` o por CPU + `h264_qsv` | `libx264` |
| Otro o desconocido | — | — | `libx264` |

Líneas de comando (la palabra `W:H` es el tamaño calculado):

```
:: NVIDIA, fase 0 (ya en el código, validada en la 3090 con un HEVC 4096 x 4096 nivel 6.0)
ffmpeg -y -hide_banner -loglevel error -nostats -progress PROG ^
  -hwaccel cuda -hwaccel_output_format cuda -i ENT -map 0:v:0 -map 0:a:0? ^
  -vf "scale_cuda=w=W:h=H" ^
  -c:v h264_nvenc -preset p5 -b:v 25M -maxrate 40M -profile:v high ^
  -c:a aac -ac 2 -b:a 192k -movflags +faststart SAL

:: AMD, fase 0 (la decodificación d3d11va es de cualquier fabricante; el escalado va en CPU)
ffmpeg -y -hide_banner -loglevel error -nostats -progress PROG ^
  -hwaccel d3d11va -i ENT -map 0:v:0 -map 0:a:0? ^
  -vf "scale=W:H:flags=bicubic,format=nv12" ^
  -c:v h264_amf -usage transcoding -quality quality -rc vbr_peak -b:v 25M -maxrate 40M -profile:v high ^
  -c:a aac -ac 2 -b:a 192k -movflags +faststart SAL

:: Intel, fase 0 (decodificación, escalado y codificación en la GPU)
ffmpeg -y -hide_banner -loglevel error -nostats -progress PROG ^
  -hwaccel qsv -hwaccel_output_format qsv -i ENT -map 0:v:0 -map 0:a:0? ^
  -vf "vpp_qsv=w=W:h=H" ^
  -c:v h264_qsv -preset slow -b:v 25M -maxrate 40M -profile:v high ^
  -c:a aac -ac 2 -b:a 192k -movflags +faststart SAL

:: Fase 1 (AMD o Intel): quitar -hwaccel y el formato de salida, y usar el filtro de CPU
::   -vf "scale=W:H:flags=bicubic,format=nv12"

:: Fase 2 (todos): CPU
ffmpeg -y -hide_banner -loglevel error -nostats -progress PROG -i ENT -map 0:v:0 -map 0:a:0? ^
  -vf "scale=W:H:flags=lanczos,format=yuv420p" ^
  -c:v libx264 -preset veryfast -crf 20 -profile:v high ^
  -c:a aac -ac 2 -b:a 192k -movflags +faststart SAL
```

Para archivos que Dan preparó de antemano (fuera del ejecutable), la receta de
`06_Unreal_standalone.md` sección 3 sigue valiendo (`libx264`, 4096 × 2048,
`-profile:v high -level:v 5.1`, `-g 30`). Con `h264_amf` el equivalente es
`-usage high_quality -quality high_quality`; con `h264_qsv`, `-preset veryslow`
o `-global_quality 21` (modo ICQ) en vez de `-b:v`.

### 4.2 Qué se validó y qué no

Con el ffmpeg de esta máquina y un HEVC Main 4096 × 4096 nivel 6.0 generado
con `libx265`:

| Cadena | Resultado |
|---|---|
| NVIDIA fase 0 (`cuda` + `scale_cuda` + `h264_nvenc`) | **funciona**: H.264 High 2048 × 2048 nivel 5.0 |
| Decodificación `d3d11va` + `scale` en CPU + `h264_nvenc` | **funciona**: la decodificación de `d3d11va` es de cualquier fabricante, así que es la base de la cadena AMD |
| Decodificación `dxva2` + `scale` en CPU | **funciona** |
| `d3d11va` con `scale_d3d11` y `hwdownload` | **falla** en la 3090 (`Could not create the texture (80070057)` y `Unsupported pixel format`). **No usar** el escalado en GPU por D3D11: por eso las cadenas AMD escalan en CPU |
| `libx264` en CPU | funciona |
| `h264_amf` y `h264_qsv` | las opciones se aceptan (los mensajes de error son de dispositivo, no de sintaxis): `DLL amfrt64.dll failed to open` y `Error creating a MFX session: -9`. **La codificación real no se probó**, no hay tarjeta AMD ni Intel |

Detalle sobre los fabricantes ante un fallo: el proceso de ffmpeg termina con
error, el controlador ya reintenta con la fase siguiente
(`DomeMediaController.cpp:2043-2045`). Basta ampliar ese encadenado a la
lista por fabricante.

Sobre un ffmpeg presente pero sin dispositivo del fabricante: comprobar que
el binario trae el codificador (`ffmpeg -hide_banner -encoders`) no prueba
que la tarjeta lo tenga. Se puede sondear con un cuadro:

```
ffmpeg -hide_banner -loglevel error -f lavfi -i nullsrc=s=256x256 -frames:v 1 -c:v h264_amf -f null -
```

(código de salida distinto de cero: sin AMF; igual con `h264_qsv`). En el
controlador es más simple dejar que las fases fallen y se encadenen.

## 5. Render: Lumen, Nanite, TSR

### 5.1 Requisitos, leídos en el motor

**Nivel de funciones.** El RHI de D3D12 solo declara el nivel SM6 si la
tarjeta cumple: nivel de funciones 12_0, modelo de shader 6.6, binding tier 3
(cuando se comprueba bindless), operaciones de ola y **atómicos de 64 bits**
(`Source/Runtime/D3D12RHI/Private/Windows/WindowsD3D12Device.cpp:391-420`). El
atómico de 64 bits lo da el propio D3D12 (`AtomicInt64OnTypedResourceSupported`),
o un mecanismo del fabricante: en AMD las intrínsecas de la extensión AGS
(`intrinsics19`, `:1456-1470`) y en Intel la emulación de la extensión INTC
(`:286-323`, `:354-382`). Sin esto la tarjeta se queda en SM5.

**Nanite.** Exige el atómico de 64 bits y SM6: Epic lo pide como «DirectX 12
con atómicos de SM6.6» ([requisitos de Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine)).
En el motor, `DoesPlatformSupportNanite` (`Source/Runtime/RenderCore/Private/RenderUtils.cpp:1274-1298`)
solo mira la plataforma de shader y el ajuste del proyecto: si la tarjeta no
llega a SM6, Nanite no está.

**Trazado de rayos por hardware.** El RHI lo activa solo con DXR 1.1, binding
tier 2 o más, bindless y plataforma SM6
(`D3D12Adapter.cpp:1296-1330`). Si falta algo escribe una línea
`Ray tracing is disabled because ...` (`:1332-1342`) y `GRHISupportsRayTracing`
queda en falso. Los mínimos de driver por fabricante
(`r.D3D12.DXR.MinimumDriverVersionNVIDIA/AMD/Intel`, `WindowsD3D12Device.cpp:72-93`)
vienen vacíos por defecto: no se impone ninguna versión de driver.
Epic lista para Lumen con trazado por hardware «AMD RX 6000 o más nuevas,
Intel Arc serie A o más nuevas y NVIDIA RTX 2000 o más nuevas» (mismo
documento de requisitos). Por el lado de Intel, su guía de UE5
([capítulo 2](https://www.intel.com/content/www/us/en/developer/articles/technical/unreal-engine-optimization-chapter-2.html))
dice que desde UE 5.5 el trazado por hardware es el camino por defecto y
recomendado en Arc, y que el de software «no se desarrolla activamente desde
hace tiempo».

**Lumen sin RT por hardware.** Si no hay DXR, Lumen cae solo al trazado por
software (`r.Lumen.HardwareRayTracing` dice «Lumen will fall back to Software
Ray Tracing otherwise»; `Source/Runtime/Renderer/Private/Lumen/LumenHardwareRayTracingCommon.cpp:16-29`
y la decisión en `:174-184`). El software usa campos de distancia y Epic
lo describe como SM6 y «una GeForce GTX 1070 o más» como referencia; el
proyecto ya genera campos de distancia (`r.GenerateMeshDistanceFields=True`
en `DefaultEngine.ini`), así que el respaldo está horneado. Una aclaración de
Epic: con RT por hardware disponible, el software puede apagarse con
`r.DistanceFields.SupportEvenIfHardwareRayTracingSupported=0` para no pagar la
memoria dos veces; este proyecto lo tiene encendido, y sirve de respaldo en las tarjetas sin DXR.

**Riesgo propio del proyecto.** `Config/DefaultEngine.ini` declara
`D3D12TargetedShaderFormats=PCD3D_SM6` y solo `D3D11TargetedShaderFormats=PCD3D_SM5`
como respaldo. Una tarjeta AMD o Intel que no llegue a SM6 (Polaris, Vega,
Intel UHD antigua) no tiene shaders de D3D12 en el paquete; qué hace el
ejecutable entonces (pasar a DX11, o no arrancar) **no se probó**
(sección 9). Además `r.RayTracing=True` está fijo para todo el proyecto: con
`r.RayTracing.EnableOnDemand=1` (el log lo confirma, «Ray tracing is enabled
(dynamic)») el RT solo se enciende cuando lo pide una función y la tarjeta lo
soporta.

### 5.2 Rendimiento esperado

**No hay ninguna medición de esta página en AMD ni en Intel.** Lo que hay:

- Medido en la RTX 3090 (perfil «Monitor», ventana 1920 × 1080 con 134 % de
  resolución interna, RT por hardware encendido, HEVC 4096 × 4096 nivel 6.0):
  unos **88 cuadros por segundo** al reproducir, y unos **3,1 GB de VRAM**
  del proceso (diferencia de `nvidia-smi` antes y durante la corrida, con el
  resto del sistema igual; es aproximada).
- De terceros, solo orientativo: en pruebas de Puget con RT activado, una RX
  6800 quedó 19 % por debajo de una RTX 3070 y una RX 6800 XT 36 % por debajo
  de una RTX 3080 en Unreal
  ([Puget Systems](https://www.pugetsystems.com/labs/articles/unreal-engine-amd-radeon-6800-6800xt-1987/)).
  RDNA2 hace el recorrido del BVH en los shaders de cómputo; el RT de NVIDIA
  lo hace por hardware.
- Nada de rendimiento en Arc se pudo confirmar con una fuente sólida.

Conclusión práctica: en una tarjeta de gama media de AMD o Intel el trazado
por hardware con el modo barato (`LightingMode 0`, la caché de superficie) es
viable; el modo caro (`LightingMode 2`, hit lighting) y la resolución de 8,3
megapíxeles del perfil «Proyector» no deben ser el valor por defecto fuera de
las RTX o las RDNA2+ grandes.

### 5.3 Perfiles de calidad por tarjeta

El controlador (`DomoPerfil` en `DomeMediaController.cpp`) ya trae cuatro perfiles, `vr`, `monitor`,
`proyector` y `ligero`, con los cvars `r.Lumen.HardwareRayTracing.LightingMode`,
`r.Lumen.Reflections.*`, `r.Lumen.ScreenProbeGather.*`, `r.ScreenPercentage` y
`r.Lumen.HardwareRayTracing`, y una selección `auto` en `ElegirPerfilAuto`
(iGPU o menos de 3 GB: `ligero`; RT por hardware y 8 GB o más: `monitor`; lo
demás: `ligero`). Esa lógica ya cubre lo esencial. Lo que esta página propone
es la correspondencia con los fabricantes y dos ajustes:

| Perfil | Para qué tarjetas | Trazado por hardware | Cvars clave (además de los del perfil) |
|---|---|---|---|
| **Alta** (`proyector`) | RTX 2070 o más, RX 6800 o más, y Arc A770 o B580 solo tras probarlas, con 12 GB o más y RT | sí; `LightingMode 2` solo en RTX y RDNA2+ de gama alta | `r.Lumen.HardwareRayTracing=1`, `r.Lumen.Reflections.DownsampleFactor=1` |
| **Media** (`monitor`) | RTX de gama baja, RX 6600 y 6700, RX 7600, Arc A580 y superiores con 8 GB | sí, con `LightingMode 0`; si aparecen artefactos o cuelgues, apagarlo | `r.Lumen.HardwareRayTracing=1` (o `0` para el respaldo por software); `r.Lumen.Reflections.DownsampleFactor=1..2`, `r.Lumen.ScreenProbeGather.DownsampleFactor=12` |
| **Media sin RT** | Tarjetas con SM6 y atómicos de 64 bits pero sin DXR 1.1 (RX 5000 y algunas Arc antiguas si el driver no expone DXR 1.1), o cualquier tarjeta cuyo trazado por hardware dé problemas | no; Lumen por software con campos de distancia | `r.Lumen.HardwareRayTracing=0`, `r.Lumen.TraceMeshSDFs.Allow=1` |
| **Baja** (`ligero`) | iGPU (Intel Iris Xe, UHD, Radeon 680M y 780M) y tarjetas de menos de 4 GB (RX 6400 y 6500 XT, Arc A380 y A310) | no | `r.Lumen.HardwareRayTracing=0`, `r.DynamicGlobalIlluminationMethod=1` con `sg.GlobalIlluminationQuality 1` (Lumen barato), o `r.DynamicGlobalIlluminationMethod=0` y `r.ReflectionMethod=2` (sin GI dinámico y con reflejos de pantalla) si aun así no sostiene |

Notas sobre estos valores:

- `r.DynamicGlobalIlluminationMethod`: 0 ninguno, 1 Lumen, 2 «Screen Space (Deprecated)», 3 plugin. `r.ReflectionMethod`: 0 ninguno, 1 Lumen, 2 pantalla
  (`Engine/Classes/Engine/EngineTypes.h:452-485`). Usar 2 en GI está marcado
  como obsoleto en el motor.
- Los escalones de `sg.GlobalIlluminationQuality` (0 a 3) y sus cvars están en
  `Config/BaseScalability.ini:318-440`: el 1 fija `r.Lumen.FinalGatherMethod=0`,
  `r.Lumen.TraceMeshSDFs.Allow=0` y `r.Lumen.HardwareRayTracing.HitLighting.Allowed=0`.
  Sirve como perfil «Baja» más barato sin salirse de Lumen.
- Intel recomienda el trazado por hardware en Arc, y la propuesta lo sigue:
  «sí, con caché de superficie» en Arc de 8 GB. El software queda como el
  interruptor de seguridad, no como el modo normal.
- Que **Arc y las RDNA2 antiguas den artefactos con Nanite o Lumen** es un
  riesgo real (algunos foros lo reportan, Epic advierte que el comportamiento
  varía en Intel) pero **no está medido aquí**.

### 5.4 Escaladores

| Escalador | ¿Viene en UE 5.8? | Fabricantes | Nota |
|---|---|---|---|
| **TSR** (`r.AntiAliasingMethod=4`) | Sí, en el motor | Todos | El proyecto ya lo usa. Tiene variantes de 16 bits por fabricante (`r.TSR.16BitVALU.AMD/Intel/Nvidia`, `Renderer/Private/PostProcess/TemporalSuperResolution.cpp:98-118`, valor 1 en los tres) y el motor apaga la de NVIDIA con drivers anteriores al 610.00 (`WindowsD3D12Device.cpp:1770-1783`; el driver de Dan es 616.92, así que no aplica). |
| DLSS | **No.** Plugin de NVIDIA | Solo RTX | Los plugins que reseñó la prensa llegan a UE 5.5; para 5.8 no lo pude confirmar. |
| FSR | **No.** Plugin de AMD | AMD; el respaldo funciona en otros | El plugin de UE 5.8 (FSR Upscaling 4.1.1, Frame Generation 4.0.1): el escalado por aprendizaje automático es para RDNA3 y RDNA4; RDNA2 y anteriores usan el analítico ([GPUOpen](https://gpuopen.com/learn/amd-fsr-plugin-updated-for-unreal-engine-58/)). |
| XeSS | **No.** Plugin de Intel | Intel (XMX) y, con el modo alterno, otros | La versión 3.1 del plugin agrega UE 5.8 (noticia de VideoCardz; la página de Intel no menciona 5.8 en su tabla) y exige DirectX 12 ([Intel](https://www.intel.com/content/www/us/en/developer/articles/technical/xess-plugin-for-unreal-engine.html)). |
| Reflex | Sí (`Plugins/Runtime/Nvidia/Reflex`) | Solo NVIDIA | Es latencia, no escalado. |

Recomendación: **quedarse con TSR**. Es el único vendor-neutral que viene con
el motor, y en un proyecto que arranca en VR (`bStartInVR`, estéreo por
instancias) sumar un plugin de terceros añade una dependencia por versión de
motor y no hay confirmación de que los tres funcionen en VR con OpenXR. El
porcentaje de pantalla ya sale del perfil (`AplicarResolucionInterna`), y
bajar la resolución interna con TSR es el remedio normal de un perfil lento.

## 6. Detección en tiempo de ejecución (C++)

| Qué | Cómo | Dónde en el motor |
|---|---|---|
| Fabricante | `IsRHIDeviceNVIDIA()`, `IsRHIDeviceAMD()`, `IsRHIDeviceIntel()`; o `GetRHIDeviceVendorId()` (devuelve `EGpuVendorId`) | `Source/Runtime/RHI/Private/RHI.cpp:1185-1245`, `RHI/Public/RHI.h:34-46` |
| Número de fabricante | `GRHIVendorId`: `0x10DE` NVIDIA, `0x1002` AMD, `0x8086` Intel | `RHIGlobals.h:826`, `RHI.cpp:1187-1200` |
| Nombre y driver | `GRHIAdapterName`, `GRHIAdapterUserDriverVersion` | `RHIGlobals.h:819`, `:821` |
| VRAM | `GRHIGlobals.GpuInfo.DedicatedVideoMemory` (bytes; 0 en muchas iGPU) | `RHIGlobals.h:143` |
| Integrada | `GRHIDeviceIsIntegrated` | `RHIGlobals.h:919` |
| Trazado por hardware | `GRHISupportsRayTracing`, `GRHISupportsInlineRayTracing` | `RHIGlobals.h:913`, `D3D12Adapter.cpp:1314-1324` |

Las macros terminan en `check(GRHIVendorId != 0)`: no se pueden llamar antes de
que el RHI esté inicializado (el controlador corre en `BeginPlay`, así que ya
está). El controlador ya las usa (`DescribirPerfil`, `DomeMediaController.cpp:2482-2492`).

Los `DeviceProfile` de Windows del motor no eligen por fabricante:
`BaseDeviceProfiles.ini` solo tiene reglas de tarjeta para Android, y en
Windows hay perfiles por plataforma (`[Windows DeviceProfile]`, línea 214).
Elegir por código en `AplicarPerfil` (como ya se hace) es lo correcto; no hace
falta un `DeviceProfile`. Para forzar una tarjeta en equipos con dos GPU
(portátiles con iGPU y tarjeta discreta): `-graphicsadapter=N`, o
`r.GraphicsAdapter`, o `-preferAMD`, `-preferIntel`, `-preferNvidia`
(`Source/Runtime/Windows/WindowsD3D/Private/WindowsD3D.cpp:42-56`,
`RHI/Private/RHI.cpp:54-64`); por defecto el RHI prefiere la no integrada, y si
hay un visor toma la que le pide el HMD (`WindowsD3D12Device.cpp:838-842`).

**VRAM mínima sugerida**, con lo medido y con criterio conservador (no medido
en AMD ni Intel):

| Perfil | VRAM dedicada | Razón |
|---|---|---|
| Alta | 12 GB o más | resolución interna de 8,3 MP, hit lighting, BVH de RT y textura de video de 4096 × 4096 |
| Media | 8 GB o más | coincide con el umbral de `ElegirPerfilAuto`; en la 3090 el proceso usó unos 3,1 GB en 1080p con RT, así que 8 GB deja margen para VR con estéreo |
| Baja | 4 GB o más (menos, aparte de las iGPU con memoria compartida) | con menos de 3 GB el controlador ya elige `ligero` |
| Video de 4096 × 4096 | la textura (`MT_Domo`, 8 bits) pesa 64 MB y el DPB del decodificador de D3D12 unas decenas de MB por cuadro (NV12): no es el cuello de botella |

## 7. Riesgos

1. **El decodificador D3D12 es el camino menos probado.** En la 3090 abrió
   los cuatro clips, pero no se sabe cómo lo reciben los drivers de AMD e Intel
   (tier, bandera de referencias, alineación). Si un driver lo acepta en
   `CheckFeatureSupport` y luego falla al decodificar, `ElectraPlayer` puede
   quedarse con un cuadro congelado en vez de fallar al abrir, y
   `AlFallarApertura` solo cubre el fallo de apertura.
2. **HEVC sin la extensión de Windows.** Sin ella, ni el decodificador MF de
   Electra ni `WmfMedia` abren HEVC; el mensaje es «no pudo abrir» y no
   avisa de la causa.
3. **Caída silenciosa a CPU dentro de Electra.** Si el decodificador de MF de
   Electra no logra asociar el dispositivo, decodifica en CPU sin dejar de
   ser `ElectraPlayer`, así que el aviso de «video pesado» (que solo mira
   `WmfMedia`, `DomeMediaController.cpp:1883`) no sale. Conviene medir cuadros
   perdidos y mostrar el aviso también por eso.
4. **SM6 obligatorio en D3D12.** Tarjetas sin SM6.6, atómicos de 64 bits o
   binding tier 3 no tienen shaders de D3D12 en el paquete; el comportamiento
   está sin probar.
5. **Seis `Failed to create pipeline state ... 80070057` al arrancar.** Salen
   también en la 3090 (`06_Unreal_standalone.md`, sección 7) y siguen sin
   investigar; otro fabricante podría tratarlos distinto.
6. **H.264 de 4096 × 2304 en AMD.** Electra lo acepta; el hardware de AMD declara
   4096 × 2176. Usar 2048 de lado o el tamaño ya recortado.
7. **Nanite y Lumen en Intel.** Epic y foros advierten de comportamiento
   variable; el parche que habilita software VRS de Nanite en Intel entró en
   UE 5.7 según terceros. Sin medir.
8. **Portátiles con dos GPU.** Si el RHI cae en la iGPU, el perfil `auto`
   elige `ligero` y el decodificador de D3D12 usa esa iGPU. Fijar la
   tarjeta con `-graphicsadapter`.
9. **Los codificadores de ffmpeg dependen del driver.** Un driver de AMD sin
   `amfrt64.dll` o de Intel sin oneVPL hace fallar la fase 0; por eso el
   encadenado de fases es obligatorio, no opcional.

## 8. Cómo se midió lo de esta página, y cómo repetirlo en otra tarjeta

Corridas del 29 de septiembre de 2026, RTX 3090 con driver 616.92, build de
`03_Unreal/Build/Windows/DomoVR.exe`, `-RenderOffscreen`. Cuatro clips de
prueba generados con ffmpeg:

```
ffmpeg -f lavfi -i testsrc2=size=4096x4096:rate=30 -t 2 -c:v libx265 -preset ultrafast -x265-params level-idc=6.0 -b:v 40M -pix_fmt yuv420p -tag:v hvc1 -movflags +faststart hevc4096_L6.mp4
ffmpeg -f lavfi -i testsrc2=size=4096x2048:rate=60 -t 2 -c:v libx265 -preset ultrafast -x265-params level-idc=5.1 -b:v 40M -pix_fmt yuv420p -tag:v hvc1 -movflags +faststart hevc4096x2048_60.mp4
ffmpeg -f lavfi -i testsrc2=size=4096x2048:rate=60 -t 2 -c:v libx264 -preset veryfast -profile:v high -level 5.2 -b:v 40M -pix_fmt yuv420p -movflags +faststart h264_4096x2048_60.mp4
ffmpeg -f lavfi -i testsrc2=size=4096x2048:rate=60 -t 2 -c:v libx265 -preset ultrafast -x265-params level-idc=5.1 -b:v 40M -pix_fmt yuv420p10le -profile:v main10 -tag:v hvc1 -movflags +faststart hevc10_4096x2048_60.mp4
```

Una playlist con los cuatro (rutas absolutas) y un guion. Para AMD o Intel, la
corrida útil es la B (D3D12 encendido, sin `NVDEC`, que ahí ni existe):

```
ElectraDecoders.bDoNotUseD3D12Video 0
domo.Cue 1
esperar 5
domo.Estado
domo.Cue 2
esperar 4
domo.Estado
domo.Cue 3
esperar 4
domo.Estado
domo.Cue 4
esperar 4
domo.Estado
quit
```

```
DomoVR.exe -RenderOffscreen -nohmd -windowed -ResX=1920 -ResY=1080 ^
  -DomoPlaylist=<playlist.json> -DomoGuion=<guion.txt> -abslog=<log> -DomoMenu=0 ^
  -LogCmds="LogD3D12VideoDecodersElectra Verbose, LogNVDECElectraDecoder VeryVerbose, LogElectraDecoders Verbose"
```

Qué mirar en el log:

| Línea | Significa |
|---|---|
| `LogD3D12VideoDecodersElectra: Verbose: Created a D3D12 video decoder.` | el clip lo decodifica D3D12 Video |
| `Decode tier 2 is needed, but tier N was returned.` | el driver informa otro tier |
| `Decode reference only allocations are not supported ...` | el driver exige referencias solo de referencia |
| `Platform rejected decoding ...` o `Decoding of W*H @ ... is not supported` | el driver rechaza ese tamaño, nivel o frecuencia |
| `LogNVDECElectraDecoder: RHI device is not from NVIDIA ...` | NVDEC se apagó solo (esperado en AMD e Intel) |
| `ElectraPlayer no pudo abrir ...; se reintenta con WmfMedia` | ningún decodificador de Electra lo aceptó |
| `Estado: ... reproductor=ElectraPlayer ... fps=` | se abrió con Electra; los `fps` y el tiempo del reloj dicen si sostiene el tiempo real |
| `Ray tracing is disabled because ...` y `Max supported Feature Level ... atomic64 ...` (`LogD3D12RHI`) | por qué el RT o SM6 no están |

Para medir CPU y decodificador de GPU, como se hizo el 29 de septiembre con el
video de Dan, usar el Administrador de tareas (motor de «Video Decode» en la
pestaña de GPU) durante la corrida.

## 9. Sin verificar

Todo lo siguiente **no se probó** porque solo hay una RTX 3090. Es lo primero
que hay que comprobar cuando haya una tarjeta AMD o Intel.

- Que el decodificador D3D12 acepte, en un driver de AMD o de Intel, H.264 y
  HEVC (incluido 4096 × 4096 nivel 6.0 a 30 cuadros y 4096 × 2048 a 60): tier 2,
  ausencia de la bandera de referencias, tamaño máximo real que informa el
  driver y el reloj del video en tiempo real.
- Que en esas tarjetas el decodificador de Media Foundation de Electra use
  realmente la GPU (DXVA) y no el respaldo por software de `bIsSW`.
- El comportamiento de los avisos: en qué momento y con qué mensaje falla un
  archivo con un driver que acepta y luego no decodifica.
- Los codificadores `h264_amf` y `h264_qsv`: las líneas de la sección 4 se
  validaron solo hasta la apertura del dispositivo. La calidad, la velocidad,
  la aceptación de `-profile:v high` y `-b:v 25M -maxrate 40M` en tarjetas
  RDNA y Arc concretas, y el rendimiento de `vpp_qsv` están sin medir.
- Los tamaños máximos de hardware de la sección 3.4: son de rocDecode,
  Wikipedia y Intel, no de una prueba de DXVA o D3D12 en cada tarjeta. Los de
  RDNA4, RDNA1, Vega y Polaris no tienen cifra firme; Vega discreta usa un
  bloque de video anterior a VCN (dato de memoria, sin fuente revisada aquí).
- Que la variable `ElectraDecoders.bDoNotUseD3D12Video` puesta desde
  `DefaultEngine.ini` (`[SystemSettings]`) se aplique a tiempo; desde el
  controlador o por consola sí se probó.
- Rendimiento de Lumen con trazado por hardware, Nanite y TSR en RDNA2, RDNA3,
  RDNA4 y Arc; los cuadros por segundo y la VRAM que se dan son solo de la 3090.
- Estabilidad de Nanite y Lumen con Arc y con las RDNA2 antiguas.
- Qué hace el ejecutable en una tarjeta sin SM6.6 o sin atómicos de 64 bits
  (`D3D12TargetedShaderFormats=PCD3D_SM6`): si cae a DX11 o no arranca.
- Si el plugin de FSR o el de XeSS funciona con OpenXR y estéreo por instancias.
- La extensión HEVC de Windows en los equipos de destino: el efecto de no
  tenerla se dedujo del código y de la documentación de Microsoft, no de una
  máquina sin ella.
- El comportamiento en una portátil con iGPU y tarjeta discreta, y en un
  equipo con dos tarjetas de fabricantes distintos.

## 10. Cambios de código

Estado a 29 de septiembre de 2026 (commit de esta misma página):

1. **Hecho: D3D12 Video encendido.** El controlador pone `ElectraDecoders.bDoNotUseD3D12Video` en 0 al
   arrancar y antes de abrir cada cue (en todos los fabricantes: en NVIDIA NVDEC tiene prioridad y D3D12 queda de
   respaldo). No se agregó una opción `Auto/Si/No` ni un comando `domo.Decodificador`: la etapa 1 del respaldo
   (punto 2) cubre el caso de un controlador que se porta mal.
2. **Hecho: respaldo por etapas.** Si Electra no abre un cue: etapa 1 con `bDoNotUseD3D12Video` en 1 (decodificador de
   Media Foundation de Electra) y etapa 2 con `WmfMedia` (CPU). Cada reintento queda en el log. No detecta cuadros
   que no avanzan con el archivo ya abierto; solo fallos de apertura.
3. **Hecho: Optimizar video por fabricante** (`LanzarFfmpeg`): NVIDIA con NVENC, AMD con `d3d11va` más `h264_amf`, Intel
   con `qsv` más `h264_qsv` y `libx264` como última fase; el tamaño de salida `W × H` se calcula en C++. Solo el camino
   NVIDIA se ejecutó de verdad; AMF y Quick Sync están por verificar.
4. **Pendiente:** el aviso de «video pesado» también cuando Electra cae a su decodificador de Media Foundation por software.
5. **Pendiente:** perfil «Media sin RT» propio. Hoy `auto` manda a `ligero` a una tarjeta sin trazado de rayos por hardware.
6. **Parcial:** el log de arranque ya escribe fabricante, nombre, VRAM y resolución (`DescribirPerfil`); falta el
   resultado de `CheckFeatureSupport` del decodificador D3D12 para el primer clip.
7. **Hecho: correcciones a `06_Unreal_standalone.md`** sobre D3D12 apagado de fábrica y HEVC de nivel 6.

## 11. Tabla final: tarjeta, qué funciona, qué hacer

«Verificado» solo aplica a la RTX 3090. Todo lo demás es esperado según el
código y las fuentes de este documento.

| Tarjeta | Video que se espera que funcione | Perfil de render | Qué hacer |
|---|---|---|---|
| NVIDIA RTX 20, 30, 40 y 50 | NVDEC: H.264, HEVC (hasta nivel 6.0 y 4096 × 4096), AV1, VP9 según la generación. **Verificado en la 3090** (H.264, HEVC Main y Main10, nivel 6.0) | Alta (12 GB o más) o Media, con RT | Nada. Ya está probado. |
| AMD RX 9000 (RDNA4) | D3D12 Video, H.264 y HEVC. Sin cifra publicada de tamaño | Alta con RT o Media | Encender D3D12; probar HEVC 4096² nivel 6.0. Sin verificar. |
| AMD RX 7000 (RDNA3) | D3D12 Video: HEVC hasta 7680 × 4320, H.264 hasta 4096 × 2176 | Alta (RX 7800 o más, 12 GB o más) o Media, con RT | Encender D3D12. H.264 de 2048 de lado. Sin verificar. |
| AMD RX 6000 grande (6700 a 6950, RDNA2) | D3D12 Video (VCN 3.0): HEVC 7680 × 4320, H.264 4096 × 2176, AV1 | Alta (12 GB o más) o Media con RT, modo `LightingMode 0` | Encender D3D12. Medir el rendimiento de RT. Sin verificar. |
| AMD RX 6600, 6600 XT, 6650 XT (8 GB) | igual que la de arriba | Media con RT | Encender D3D12; si el RT pesa, `r.Lumen.HardwareRayTracing=0`. |
| AMD RX 6400, 6500 XT (4 GB, Navi 24) | H.264, HEVC, VP9 por hardware; **sin AV1** | Baja | Perfil Baja; video en H.264 de 2048. |
| AMD RX 5000 (RDNA1) y anteriores (Vega, Polaris) | H.264 y HEVC hasta «4K» sin cifra firme; sin DXR | Media sin RT si tiene SM6.6 y atómicos de 64 bits; si no, incierto | Optimizar video a H.264 de 2048 con `h264_amf`. No contar con HEVC 4096² nivel 6.0. |
| AMD iGPU (Radeon 680M, 780M y equivalentes) | H.264 y HEVC por D3D12 o MF | Baja | Perfil Baja; H.264 de 2048; comprobar VRAM compartida. |
| Intel Arc A750, A770, B570, B580 (8 GB o más) | D3D12 Video: HEVC hasta 16K; H.264 «4K»; AV1 | Media con RT (caché de superficie) | Encender D3D12; probar HEVC 4096² nivel 6.0; ver artefactos de Nanite y Lumen. Sin verificar. |
| Intel Arc A380, A310 (6 GB o menos) | HEVC 16K, H.264 4K, AV1 | Baja | Perfil Baja; H.264 de 2048 con `h264_qsv`. |
| Intel iGPU Xe (Iris Xe, Arc de Core Ultra) | HEVC 16K en Gen 11 a 13; H.264 4K | Baja (Media solo con memoria y RT y 8 GB reales) | Perfil Baja; H.264 de 2048; comprobar VRAM compartida. |
| Intel UHD anterior (Gen 9 y 10) | HEVC 8K y H.264 4K, sin AV1 | Baja, probablemente sin SM6 | Comprobar que arranca en D3D12; si no, no se soporta. |
| Cualquier otra | H.264 de 2048 por Media Foundation | Baja | `libx264` como copia liviana. |

## Fuentes

- Motor UE 5.8: rutas y líneas citadas en el texto, en
  `C:\Program Files\Epic Games\UE_5.8\Engine`.
- Microsoft: [D3D12_VIDEO_DECODE_TIER](https://learn.microsoft.com/en-us/windows/win32/api/d3d12video/ne-d3d12video-d3d12_video_decode_tier),
  [D3D12_VIDEO_DECODE_CONFIGURATION_FLAGS](https://learn.microsoft.com/en-us/windows/win32/api/d3d12video/ne-d3d12video-d3d12_video_decode_configuration_flags),
  [D3D12_FEATURE_DATA_VIDEO_DECODE_SUPPORT](https://learn.microsoft.com/en-us/windows/win32/api/d3d12video/ns-d3d12video-d3d12_feature_data_video_decode_support),
  [decodificador H.265 de Media Foundation](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/medfound/h-265---hevc-video-decoder.md).
- AMD: [rocDecode, códecs y arquitecturas](https://rocm.docs.amd.com/projects/rocDecode/en/latest/reference/rocDecode-formats-and-architectures.html),
  [Video Core Next (Wikipedia)](https://en.wikipedia.org/wiki/Video_Core_Next),
  [Recommended FFmpeg Encoder Settings (AMF)](https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/Recommended-FFmpeg-Encoder-Settings),
  [plugin de FSR para UE 5.8](https://gpuopen.com/learn/amd-fsr-plugin-updated-for-unreal-engine-58/).
- Intel: [Features and Formats (oneVPL)](https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/details.html),
  [Video Codecs Supported by Intel Arc GPUs](https://www.intel.com/content/www/us/en/support/articles/000098345/graphics.html),
  [Unreal Engine optimization, capítulo 2](https://www.intel.com/content/www/us/en/developer/articles/technical/unreal-engine-optimization-chapter-2.html),
  [plugin de XeSS](https://www.intel.com/content/www/us/en/developer/articles/technical/xess-plugin-for-unreal-engine.html),
  [XeSS 3.1 con UE 5.8 (VideoCardz)](https://videocardz.com/newz/intel-xess-plugin-3-1-adds-unreal-engine-5-8-support).
- Epic: [requisitos de hardware y software](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine),
  [Lumen, detalles técnicos](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-technical-details-in-unreal-engine).
- Rendimiento: [Puget Systems, Unreal Engine con RX 6800 y 6800 XT](https://www.pugetsystems.com/labs/articles/unreal-engine-amd-radeon-6800-6800xt-1987/).
