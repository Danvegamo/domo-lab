# El puente Spout: TouchDesigner → cúpula de Unreal

Cómo llega en vivo la imagen de TouchDesigner a la cúpula de la sala descrita en
[02_Sala_Unreal.md](02_Sala_Unreal.md): el plugin, la clase que recibe la señal,
el script que la deja montada, el formato que debe mandar TouchDesigner, el
crash que hubo que arreglar y cómo comprobar que la señal llega. Todo corre en
el mismo equipo Windows; Spout comparte texturas por GPU, no por red. El
receptor del plugin tiene dos caminos (`SpoutReceiver.cpp:457-466`): el
principal toma la textura compartida de DirectX directamente en la GPU, y el de
respaldo copia los píxeles por CPU. Cuál se usa lo decide lo que devuelva la
librería de Spout en cada recepción, no una opción del proyecto.

## 1. Por qué Spout y no NDI

Unreal 5.8 trae de fábrica un plugin `NDIMedia` de Epic, ya compilado, que no
exige C++. Se evaluó primero, pero la decisión fue ir por Spout: TouchDesigner y
Unreal están en la misma máquina y Spout comparte la textura directamente en la
GPU, sin codificar ni pasar por la red. El costo es que un plugin con código
obliga a que `DomoVR` tenga su propio módulo C++ (`Source/DomoVR/`) y a compilar
antes de abrir el editor. NDI no quedó habilitado ni deja rastro; sigue
disponible en el motor si algún día se prefiere la ruta sin compilar, igual que
el kit comercial de Off World Live (Fab), con binarios para Spout y NDI.

## 2. El plugin

| Dato | Valor |
|---|---|
| Repositorio | `https://github.com/kessoning/Spout-UE5`, fork del original de `zuyi53` |
| Rama y commit | `5.8_fix`, commit `ac7f9fb` ("Added 5.8 support"); no la rama `main` |
| Versión | `0.0.5` según `CHANGELOG.md`: corrige la firma de `FSlateRenderer::OnBackBufferReadyToPresent` que cambió en 5.8 |
| Ubicación en el repo | `03_Unreal/DomoVR/Plugins/SpoutPlugin/` (vendorizado, con `ThirdParty/Spout/` y `Spout.dll`) |
| Requisito | RHI D3D12 (el plugin usa interoperabilidad D3D11 sobre DX12); solo Win64 |
| Licencia | el `README.md` dice "MIT License. See the LICENSE file", pero la rama clonada **no trae archivo `LICENSE`** |

Sobre la licencia: la única evidencia hoy es esa frase del README, no un archivo
versionado. Antes de usar esto en trabajo de cliente conviene confirmarlo con
el autor o revisar otra rama o tag.

El plugin vendorizado **no es idéntico al del repositorio**: trae el arreglo de
la sección 7 en `Source/SpoutPlugin/Public/SpoutModule.h`,
`Private/SpoutModule.cpp` y `Private/SpoutD3DContext.cpp`. Además, `FindSpoutDllPath()` en `Private/SpoutModule.cpp` busca
`Spout.dll` también junto al `.exe`, que es donde queda en un build empaquetado
(ver [06_Unreal_standalone.md](06_Unreal_standalone.md), sección 6). Si se actualiza el
plugin desde el origen hay que volver a aplicar ese cambio.

La compilación (comando de `UnrealBuildTool` con el editor cerrado) está en
[02_Sala_Unreal.md](02_Sala_Unreal.md), sección 8. Genera
`UnrealEditor-SpoutPlugin.dll` y copia `Spout.dll` a
`Plugins/SpoutPlugin/Binaries/Win64/`. Los dos avisos `C4996` por
`RHIUpdateTexture2D` (obsoleto en 5.8, todavía funcional) salen de
`SpoutReceiver.cpp` del plugin, no de `DomoVR`.

## 3. La clase `ASpoutDomeReceiver`

Vive en `03_Unreal/DomoVR/Source/DomoVR/SpoutDomeReceiver.{h,cpp}` y es la única
clase de juego del módulo. Se resolvió en C++ y no en Blueprint por una razón
técnica, además de que nadie quería cablear nodos a mano: la función del plugin
`USpoutBPFunctionLibrary::SpoutReceiver` recibe el material dinámico (`OutMat`)
por referencia y solo crea uno nuevo si llega nulo. Desde Blueprint ese pin no
tiene memoria entre llamadas y, sin promoverlo a variable y pasarlo de vuelta,
se crea una Dynamic Material Instance nueva por frame. En C++ se guarda en un
`UPROPERTY()` y se reutiliza. (El parámetro `OptionalOutputRenderTarget` sí se
usa en la implementación aunque el comentario del plugin diga "reserved for
future"; esta clase no lo necesita.)

Propiedades editables en el panel de detalles, sin recompilar:

| Propiedad | Valor por defecto | Qué es |
|---|---|---|
| `Spout Sender Name` | `TD_Domo_Lab` (constante de `conectar_spout.py`, línea 60, y valor en el nivel) | nombre exacto del sender de TouchDesigner. Los nombres anteriores fueron `TD_Domo_Final` (un proyecto anterior del autor) y `TDSyphonSpoutOut` (dosis.45, sigue como valor por defecto en el código C++). Se lee en cada Tick, así que se cambia en vivo |
| `Target Material` | `MI_Domo` | material del que se crea la instancia dinámica |
| `Texture Parameter Name` | `SpoutTexture` | parámetro de textura de `M_Domo` que recibe el frame |
| `Target Mesh Component` | el `StaticMeshComponent` de `Domo_Actor` | malla a la que se aplica el material |
| `Target Material Slot` | 0 | ranura de material de esa malla |

Comportamiento:

- `Tick()` llama a `SpoutReceiver` con el material y la textura guardados y
  aplica el material a la malla solo la primera vez que cambia de puntero, no
  cada frame. Lee `SpoutSenderName` en cada Tick, así que **el nombre del
  sender se cambia en vivo** desde el panel de detalles.
- Tickea también en el editor sin darle a Play: sobreescribe
  `ShouldTickIfViewportsOnly()` para devolver `true`, que es el mecanismo real
  del motor para eso.
- Si el sender no existe todavía (TouchDesigner cerrado), no hace nada salvo un
  aviso en el log cada 5 segundos como máximo.
- Si `Spout.dll` no cargó, se apaga solo (`SetActorTickEnabled(false)`) y lo
  dice una vez. Ver la sección 7.

## 4. `conectar_spout.py`

Se corre igual que `importar_sala.py` (headless con el editor cerrado, o pegado
en la consola de Python del editor abierto), siempre **después** de
`importar_sala.py`, porque la reimportación reconstruye el nivel y borra el
receptor. Pasos:

1. Confirma que `SpoutPlugin` cargó (`unreal.SpoutBPFunctionLibrary` existe).
2. Borra el Blueprint antiguo `BP_SpoutDomoReceiver` si quedaba alguno.
3. Asegura que `Domo_Actor` lleve `MI_Domo` en su ranura 0.
4. Coloca una instancia de `ASpoutDomeReceiver` (borrando las previas) con
   `SPOUT_SENDER_NAME = "TD_Domo_Lab"`, `MI_Domo`, `SpoutTexture` y la malla
   de `Domo_Actor`.
5. Vuelve a pasar el indicador de uso Nanite sobre los materiales de la sala.
6. Guarda el nivel y los assets, y genera `.mcp.json` (sección 9).

## 5. Lo que debe mandar TouchDesigner

| Dato | Valor |
|---|---|
| Nombre del sender | `TD_Domo_Lab` (actual, `conectar_spout.py` línea 60). Nombres anteriores: `TD_Domo_Final` (un proyecto anterior del autor) y `TDSyphonSpoutOut` (proyecto `dosis.45`). El receptor lee el nombre en cada Tick: se cambia en vivo desde el panel de detalles |
| Formato | equirectangular 2:1 completo, 4096 × 2048 |
| Contenido útil | la mitad superior: horizonte en V = 0,5, 45° de elevación en V = 0,75, cénit en V = 1,0; la mitad inferior no se ve en la cúpula (verificado el 17 de septiembre de 2026, ver sección 10) |
| Origen | fisheye 180 (domemaster) convertido a equirectangular con un `Projection TOP`, fov 180, rx = −90 |
| Girar el azimut | con **rz**, no con ry |

La cúpula tiene UV con U = azimut (vuelta completa) y V = elevación, así que un
equirectangular se envuelve sobre ella sin corrección del lado de Unreal. Si el
sender cambia de nombre, basta con editar `Spout Sender Name` en el actor
`SpoutDomeReceiver` del nivel (o la constante de `conectar_spout.py`).

## 6. Espacio de color

La textura transitoria que crea el receptor no toca la bandera `SRGB`, así que
queda en el valor por defecto de cualquier textura nueva de Unreal: `SRGB =
true`. Es lo correcto: TouchDesigner emite gráficos convencionales codificados
en gamma sRGB (el propio README del plugin recomienda `RTF RGBA8 sRGB` como
formato más confiable), y con esa bandera la GPU los decodifica a lineal al
muestrear, que es lo que espera el pin de Emissive Color. No hay que configurar
nada. Si la cúpula se ve lavada o apagada, el lugar a revisar es la cadena de
TouchDesigner (formato de salida del `Syphon Spout Out`), no el sRGB de Unreal.

**El receptor solo lee texturas de 8 bits por canal** (medido el 17 de
septiembre de 2026). Si TouchDesigner manda una textura de 16-bit float, que es
lo que sale del sistema de pantallas `VIDEO_DOME` y de cualquier cadena que lo
herede, `SpoutReceiver` devuelve falso y `ASpoutDomeReceiver` se queda mostrando
el último frame que pudo leer, sin avisar en pantalla: solo aparece el aviso
"no disponible todavia" cada unos 5 segundos en el log. El síntoma es una
cúpula que parece congelada en un cuadro viejo aunque TouchDesigner muestre
otra cosa. El arreglo va del lado de TouchDesigner: un Reorder TOP (o cualquier
TOP) con formato `rgba8fixed` justo antes del `Syphon Spout Out`; en
`build_domo.py` ese nodo es `alfa_unreal`. La prueba que lo destapó fue un
`constant` rojo de 8 bits, que sí llegaba mientras la cadena completa no.

## 7. El crash `ERROR_MOD_NOT_FOUND` (`0xC06D007E`) y su arreglo

Es un fallo del plugin original en la rama `5.8_fix`, no de este proyecto.

**Síntoma**: el editor se cerraba solo, de forma repetible, con volcados en
`Saved/Crashes/` y esta pila en `Saved/Logs/DomoVR.log`:

```
Unhandled Exception: 0xc06d007e
UnrealEditor-SpoutPlugin.dll!__delayLoadHelper2() [delayhlp.cpp:346]
UnrealEditor-SpoutPlugin.dll!FSpoutD3DContext::Initialize() [SpoutD3DContext.cpp:90]
UnrealEditor-SpoutPlugin.dll!FSpoutReceiver::Receive() [SpoutReceiver.cpp:405]
UnrealEditor-DomoVR.dll!ASpoutDomeReceiver::Tick() [SpoutDomeReceiver.cpp:81]
```

**Causa**: `0xC06D007E` es `ERROR_MOD_NOT_FOUND` envuelto por el ayudante de
carga diferida del CRT. El plugin declara `Spout.dll` como `PublicDelayLoadDLLs`
y la copia a `Plugins/SpoutPlugin/Binaries/Win64/`, pero su `StartupModule()`
solo comprobaba que el archivo existiera; nunca lo cargaba. La primera llamada
a la DLL dispara la carga diferida, que busca `Spout.dll` por nombre pelado con
el orden de búsqueda de Windows, que no incluye la carpeta del plugin. Falla
como excepción estructurada, que un `catch(...)` no detiene, y tumba el proceso.

**Arreglo**, en el plugin vendorizado:

1. `FSpoutModule::StartupModule()` carga `Spout.dll` explícitamente con
   `FPlatformProcess::GetDllHandle()` desde su ruta absoluta y libera el handle
   en `ShutdownModule()`. Con el módulo ya cargado bajo ese nombre, la carga
   diferida lo resuelve sin buscar.
2. Blindaje en tres capas: `FSpoutModule::IsSpoutRuntimeAvailable()` queda en
   `false` si la carga falla (un error en el log, una sola vez);
   `FSpoutD3DContext::Initialize()` lo comprueba antes de tocar la biblioteca; y
   `ASpoutDomeReceiver::Tick()` lo comprueba antes de llamar a `SpoutReceiver` y
   se apaga solo si no está. Cúpula sin señal en vez de editor caído.

Verificado: con `Spout.dll` renombrada, una llamada headless a `spout_receiver`
ya no crashea (el log dice `Spout.dll no esta disponible en este proceso`, código
de salida 0); con la DLL repuesta, el editor quedó estable con y sin
TouchDesigner, sin volcados nuevos.

## 8. Cómo comprobar que llega señal

1. TouchDesigner abierto con el `Syphon Spout Out` activo y el nombre de sender
   que espera el receptor (`TD_Domo_Lab`).
2. Abrir el proyecto; el mapa `/Game/Maps/DomoVR` ya trae `SpoutDomeReceiver`.
   Desde el 18 de septiembre de 2026 los niveles arrancan con la fuente
   *Media* (los videos de la playlist, ver [06_Unreal_standalone.md](06_Unreal_standalone.md)),
   que apaga el receptor: poner `Fuente = Spout` en el actor
   `DomeMediaController` o correr `domo.Fuente Spout` en la consola.
3. Viewport en **Realtime** (`Ctrl+R`) o en Play. Un viewport pausado, que es el
   estado al abrir el editor o al lanzarlo sin foco, no tickea ningún actor.
4. Viewport en modo **Lit**: en Unlit los materiales sin iluminación se dibujan
   como un gris plano uniforme, con cualquier intensidad.
5. La cúpula muestra la imagen en vivo y las butacas cambian de tono con ella.
   Si se ve la textura de marcador de posición, revisar en `Saved/Logs/DomoVR.log`
   los avisos de `ASpoutDomeReceiver` (`LogTemp`) y `LogSpoutPlugin`.
   Si la cúpula muestra un cuadro viejo que no cambia aunque TouchDesigner sí
   cambie, y el log repite "no disponible todavia" cada ~5 s, el sender está
   mandando 16-bit float: el receptor solo lee 8 bits por canal (sección 6).
   Confirmar que el TOP anterior al `Syphon Spout Out` (`alfa_unreal`) tenga
   formato `rgba8fixed`; un `constant` rojo de 8 bits sirve como prueba de
   que el camino funciona.
6. Sin depender del render: por MCP, `CaptureAssetImage` sobre la textura del
   parámetro `SpoutTexture` de la instancia dinámica (`MID_MI_Domo_0`) muestra
   el frame real de TouchDesigner. Así se confirmó que la señal llega al material.

## 9. Control por MCP

Unreal 5.8 trae de fábrica un servidor MCP. Están habilitados
`ModelContextProtocol` (el servidor) y `EditorToolset` (actores, propiedades y
assets); otros toolsets (UMG, Sequencer) no se prendieron porque el proyecto no
los usa.

- Escucha en `http://127.0.0.1:8090/mcp`, sin autenticación, solo localhost.
  El puerto se fija en `Config/DefaultEditorPerProjectUserSettings.ini`
  (`bAutoStartServer=True`, `ServerPortNumber=8090`, `ServerUrlPath=/mcp`).
  El 8000 de fábrica no liga en esta máquina porque Windows reserva el rango
  7929–8028 (NAT de Hyper-V). En otra máquina puede volver a 8000 si está libre.
- Arranca solo al abrir el editor. A mano, desde la consola del editor:
  `ModelContextProtocol.StartServer 8090` y `ModelContextProtocol.StopServer`.
- La configuración del cliente la genera
  `ModelContextProtocol.GenerateClientConfig ClaudeCode` (lo dispara
  `conectar_spout.py`) y queda en `03_Unreal/DomoVR/.mcp.json` con la URL de
  arriba.
- Con el editor en segundo plano, Unreal baja a unos 3 fps y el receptor tickea
  a esa velocidad. Se apagó `bThrottleCPUWhenNotForeground` en la configuración
  del editor del usuario (`%LOCALAPPDATA%\UnrealEngine\5.8\Saved\Config\WindowsEditor\EditorSettings.ini`),
  que no está en el repositorio.
- Las herramientas de `EditorToolset` piden parámetros que su esquema marca como
  opcionales (`CaptureViewport` exige `captureTransform` y `annotations: []`);
  conviene mandar el objeto completo con valores vacíos.

## 10. Pendiente de confirmar

- **Mitad superior del equirectangular: resuelto en la práctica.** Verificado
  el 17 de septiembre de 2026 con un patrón de bandas enviado por Spout
  (capturas en `05_Preview/pruebas/unreal_bandas_lateral.png` y
  `unreal_bandas_cenit.png`): la cúpula muestra solo la mitad superior del
  equirectangular. V = 0,5 cae en el horizonte (la línea de arranque de la
  cúpula sobre los listones), V = 0,75 en 45° de elevación y V = 1 en el cénit.
  U = 0,5 cae en +X (el frente del público, opuesto a la zona de control en
  −X), y los meridianos dibujados cada 45° salieron equiespaciados. Es decir,
  TouchDesigner debe seguir mandando el equirectangular 2:1 completo con el
  horizonte en V = 0,5, tal como hace hoy. **Resuelto también en el código**
  (18 de septiembre de 2026): la cúpula se creaba con
  `primitive_uv_sphere_add`, que ya traía una capa `UVMap` (canal 0) con
  `U = azimut/360 + 0,5` y `V = 0,5 + elevación/180`; el script de
  `01_Blender/generar_sala_domo.py` escribía su fórmula `V = elevación / 90` en
  una segunda capa (`UVMap.001`, canal 1), y Unreal muestrea el canal 0. Por
  eso la cúpula leía la mitad superior. Ahora la cúpula se construye a mano con
  una sola capa y esa misma fórmula (`V = 0,5 + elevación/180`) en los tres
  modelos de sala (180, 90 y 45), sin normalizar al casquete. Detalle en
  [05_Modelos_de_sala.md](05_Modelos_de_sala.md), sección 3.
- **Verificación visual final.** Con datos duros quedó demostrado que el frame
  de Spout llega hasta la instancia dinámica de `MI_Domo`. Las notas del 17 de
  septiembre de 2026 indican que con `is_sky` y `SkyLight_Domo` la sala deja de
  quedar negra, pero no hay captura archivada en el repositorio que lo muestre.
- **`RHIUpdateTexture2D` obsoleto** en el plugin (compila en 5.8, puede romper
  en 5.9) y **licencia** sin archivo `LICENSE` en la rama usada.
