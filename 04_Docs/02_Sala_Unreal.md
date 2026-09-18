# La sala de domo en Unreal Engine 5.8

Este documento describe el proyecto `03_Unreal/DomoVR`: una sala de planetario
(cúpula, muro cilíndrico, 360 butacas) que se recorre en realidad virtual y cuya
cúpula muestra en vivo lo que TouchDesigner envía por Spout. Aquí está la
geometría, el contrato de unidades, cómo regenerar todo desde cero, los
materiales, la iluminación, el post proceso y la ruta de VR. El puente con
TouchDesigner tiene su propio documento: [03_Puente_Spout.md](03_Puente_Spout.md).
La bitácora cronológica completa, con los callejones sin salida, está en
[Unreal_sala_domo.md](Unreal_sala_domo.md).

## 1. Qué es

Un proyecto de Unreal 5.8 con Lumen, DX12 y OpenXR que carga un solo nivel,
`/Game/Maps/DomoVR`, con la sala entera. Toda la sala (mallas, materiales,
nivel, luces, post proceso, punto de partida) se construye por script; nada se
arma a mano en el editor. La lógica en tiempo de ejecución es mínima: un único
actor en C++ (`ASpoutDomeReceiver`) que recibe la señal de Spout y la aplica a la
cúpula. El resto del proyecto no tiene código propio.

## 2. Dónde vive cada cosa

```
01_Blender/generar_sala_domo.py    genera la sala en Blender y exporta FBX, glTF y texturas
02_Export/sala_domo.fbx            la geometría que consume Unreal
02_Export/texturas/                mapas PBR horneados (BaseColor, Roughness, Normal; 2048x2048)
03_Unreal/importar_sala.py         importa el FBX, crea materiales y arma el nivel
03_Unreal/conectar_spout.py        coloca el receptor de Spout (ver 03_Puente_Spout.md)
03_Unreal/abrir_proyecto.ps1       abre el editor gráfico
03_Unreal/importar_sala.ps1        corre importar_sala.py sin interfaz (headless)
03_Unreal/crear_media_domo.py      la version sin TouchDesigner: video en la cupula (ver 06_Unreal_standalone.md)
03_Unreal/empaquetar.ps1           empaqueta la sala como DomoVR.exe (Win64, Development)
03_Unreal/DomoVR/                  el proyecto de Unreal (uproject, Config, Source, Plugins, Content)
```

Dentro del proyecto, el contenido queda en `Content/Sala/` (mallas, y las
subcarpetas `Materials/` y `Textures/`) y el nivel en `Content/Maps/DomoVR.umap`.
`Binaries/`, `Intermediate/`, `Saved/` y `DerivedDataCache/` los regenera el
editor y están fuera del control de versiones.

## 3. Geometría y contrato de unidades

La sala es un cilindro cerrado de 11,5 m de radio con piso plano (sin grada),
muro de 3 m de alto y una cúpula hemisférica que arranca a esa altura. No hay
ningún volumen exterior: el puesto de control es un sector dentro del mismo
cilindro. Todo se genera desde las constantes de `01_Blender/generar_sala_domo.py`.

| Parámetro | Valor | Nota |
|---|---|---|
| Radio del domo y del muro | 11,5 m | escala del Planetario de Bogotá |
| Altura del ecuador de la cúpula | 3 m | el muro cilíndrico va del piso a esa altura |
| Teselado de la cúpula | 128 × 64 | segmentos de azimut × elevación (media esfera) |
| Tarima central | 3 m de diámetro × 1 m de alto | en el origen; el PlayerStart no puede caer ahí |
| Sector de control | 7 m de arco sobre el muro, desde 6,5 m de radio | lado −X, sin butacas; consola y marca en el piso |
| Butacas | 360 = 6 cuñas × 60 | reclinadas 40° hacia atrás; espectador casi acostado |
| Filas por cuña | 7, radios de 3,2 a 10,4 m | paso radial 1,2 m; paso entre butacas 0,6 m; se calculan, no se escriben |
| Puertas | 4, de 1,4 × 2,3 m | dos flanquean el control, dos simétricas en el lado opuesto |
| Listones de madera | ancho 7 cm, paso 14 cm | revestimiento vertical del muro, material `M_Madera` |

Mallas que trae el FBX y material que recibe cada una:

| Malla | Material | Comentario |
|---|---|---|
| `SM_Domo` | `MI_Domo` (instancia de `M_Domo`) | normales hacia adentro; UV con U = azimut, V = elevación |
| `SM_Muro`, `SM_Piso`, `SM_Tarima` | `M_Muro`, `M_Piso`, `M_Tarima` | PBR horneado |
| `SM_Listones` | `M_Madera` | PBR horneado |
| `SM_Control` | `M_Control` | color plano; no se hornea textura |
| `SM_Butacas_01` … `SM_Butacas_06` | `M_Butaca` | una malla por cuña, 60 butacas fusionadas |
| `SM_Puerta_01` … `SM_Puerta_04` | `M_Puerta` | con hueco real en el muro |

En total son unos 43 000 triángulos. Por eso Nanite queda apagado
(`USAR_NANITE = False` en `importar_sala.py`): a ese conteo no aporta nada y su
indicador de uso en los materiales fue fuente de avisos. Si algún día entra un
escaneo por fotogrametría, esa constante es lo único que hay que voltear.

### Unidades: Blender → FBX → Unreal

Blender trabaja en metros y Unreal en centímetros. El FBX declara su unidad, y
la conversión la hace el importador de Unreal: `importar_sala.py` fija
`convert_scene_unit = True` en `FbxStaticMeshImportData`, cuyo valor de fábrica
es `False`. Sin esa bandera la sala entraba como una maqueta de 23 cm de
diámetro (el domo medía ±11,5 uu) y se veía negra porque todo quedaba dentro
del plano de recorte cercano de la cámara. Se corrigió del lado de Unreal, no
en el export de Blender, porque el mismo FBX también produce el `.glb` y
cambiar la escala de origen afectaría a todos sus consumidores.

Cotas verificadas en el nivel después de la corrección (`get_actor_bounds`):

| Actor | Mínimo (uu) | Máximo (uu) |
|---|---|---|
| `Domo_Actor` | (−1150, −1150, 300) | (1150, 1150, 1450) |
| `Muro_Actor` | (−1150, −1150, 0) | (1150, 1150, 300) |
| `Piso_Actor` | (−1150, −1150, 0) | (1150, 1150, 0) |
| `Tarima_Actor` | (−150, −150, 0) | (150, 150, 100) |

Un detalle del importador: cuando el nodo de origen no tiene nombre único, los
Static Mesh llegan con el nombre del archivo antepuesto (`sala_domo_SM_Domo`).
El script resuelve los nombres por sufijo, así que acepta ambas formas.

## 4. Cómo regenerar la sala

La cadena completa, en orden:

1. **Blender** (sin interfaz):
   `blender.exe --background --python 01_Blender/generar_sala_domo.py`.
   Borra la escena, la reconstruye desde las constantes, hornea las texturas
   PBR con Cycles, exporta `02_Export/sala_domo.fbx` y `.glb`, y renderiza
   vistas de comprobación en `05_Preview/`.
2. **Importar en Unreal**: `03_Unreal/importar_sala.ps1` (headless, escribe
   `03_Unreal/Saved_Logs/importar_sala.log`) o, si el editor ya está abierto,
   pegar `importar_sala.py` en su consola de Python. Nunca las dos cosas a la
   vez: dos procesos de Unreal sobre el mismo `.uproject` se pelean por
   `Saved/`, `Intermediate/` y el `.umap`.
3. **Conectar Spout**: `conectar_spout.py`, después del anterior, porque
   reimportar reconstruye el nivel desde cero y borra el receptor.

`importar_sala.py` hace, en este orden: importa el FBX a `/Game/Sala/` con
`combine_meshes = False` (una malla por objeto); busca e importa las texturas de
`02_Export/texturas/` (BaseColor como color sRGB, Roughness como `TC_Masks` sin
sRGB, Normal como `TC_Normalmap` sin sRGB); crea los materiales; carga o crea el
nivel y lo vacía de actores; coloca un `StaticMeshActor` por malla; crea el
`PostProcessVolume`, el `SkyLight_Domo` y el `PlayerStart`; guarda todo e
imprime un resumen. Los mensajes salen como `Warning` con prefijo
`[importar_sala]` porque en modo `-run=pythonscript` los `Display` no siempre
llegan al log.

Es idempotente: cada material, textura e instancia se borra y se recrea; el
nivel se conserva pero se limpia. Ningún `None` sigue de largo: si un asset no
se crea o una malla no se coloca, el script para con una excepción que nombra
el asset. Si el FBX no existe todavía, no falla: construye el resto del nivel y
lo deja anotado. Las mallas se colocan con `spawn_actor_from_class` más
`set_static_mesh`, no con `spawn_actor_from_object`: esa última depende de un
viewport de editor vivo y en headless devuelve `None` en silencio.

## 5. Materiales y por qué la cúpula ilumina la sala

La única fuente de luz de la sala es la propia cúpula. `importar_sala.py` quita
del nivel cualquier `DirectionalLight`, `ExponentialHeightFog` o `SkyAtmosphere`,
y arma la cadena así:

| Pieza | Configuración | Para qué |
|---|---|---|
| `M_Domo` | shading model Unlit, `two_sided`, `is_sky` | mostrar solo su emisión; verse desde adentro sin depender de las normales; contar como cielo |
| Grafo de `M_Domo` | `SpoutTexture` (TextureSampleParameter2D) × `EmissiveIntensity` (escalar) → Emissive Color | la textura la sustituye Spout en vivo; la intensidad se ajusta sin recompilar |
| `EmissiveIntensity` | parámetro escalar de `M_Domo`, valor inicial 1,0 (`importar_sala.py`, línea 185); expuesto en `MI_Domo` | multiplica el frame de Spout antes del pin Emissive Color; se ajusta en vivo desde `MI_Domo` sin recompilar. El valor que se ve bien no está confirmado visualmente |
| Textura de arranque | `/Engine/EngineResources/DefaultTexture` | marcador de posición sRGB; con la grilla lineal el material no compilaba y el domo salía negro |
| `MI_Domo` | instancia de `M_Domo` | es la que lleva la malla y de la que el receptor crea su instancia dinámica |
| `SkyLight_Domo` | en (0, 0, 400), movable, `real_time_capture`, `lower_hemisphere_is_black`, intensidad 2 | captura la cúpula cada frame y la reparte como luz sobre butacas, piso y listones |

El punto clave es `is_sky` más el SkyLight con captura en tiempo real. Lumen
por sí solo casi no recoge la emisión de una malla enorme y delgada como la
cúpula: sin esas dos piezas la sala queda negra aunque la cúpula se vea
encendida. Marcada como cielo, el `SkyLight_Domo` la lee cada frame y con ella
tiñe la sala con los colores de lo que se proyecta.

Los demás materiales son Default Lit con los mapas horneados (BaseColor →
Base Color, Roughness canal R → Roughness, Normal → Normal), metálico fijo en 0.
Si falta un mapa, el material cae a un color plano oscuro y mate con parámetros
`Color` y `Roughness` expuestos. `M_Control` siempre cae al color plano porque no
se hornea.

## 6. Post proceso

Un `PostProcessVolume` sin límites (`Unbound`), etiquetado `PPV_ExposicionFija`.
La exposición es manual y fija: con exposición automática la cámara reaccionaría
a la propia imagen proyectada y arruinaría la lectura del contenido.

| Ajuste | Valor |
|---|---|
| Método de exposición | Manual |
| Exposición física de cámara | apagada (con ella la emisión del domo quedaba hundida en negro) |
| Exposure bias | −0,5 |
| Brillo mínimo y máximo | 1,0 / 1,0 |
| Indirect lighting intensity | 8 |
| Lumen scene lighting quality | 2 |
| Bloom intensity | 0,15 |

En `Config/DefaultEngine.ini` acompañan: Lumen para GI y reflejos
(`r.DynamicGlobalIlluminationMethod=1`, `r.ReflectionMethod=1`), campos de
distancia activos, exposición automática apagada por defecto, DX12 como RHI
(`DefaultGraphicsRHI_DX12`, SM6), sin iluminación estática y con
`EditorStartupMap`/`GameDefaultMap` apuntando a `/Game/Maps/DomoVR`.

## 7. VR (OpenXR)

En Unreal 5.8 no existe un plugin aparte de SteamVR: SteamVR actúa como runtime
OpenXR del sistema y el motor habla con él por el plugin `OpenXR` estándar. El
proyecto lleva `bStartInVR=True` y `vr.InstancedStereo=1`.

1. Encender el visor y conectarlo al PC con Virtual Desktop Streamer (por red).
2. Arrancar SteamVR y confirmar que su runtime OpenXR es el activo del sistema.
3. Abrir el proyecto y el mapa `/Game/Maps/DomoVR`.
4. Play → **VR Preview** (no el Play normal en el viewport).

En cada arranque el log muestra `xrCreateInstance called with invalid API
version 1.1. Max supported version is 1.0`, impreso por el loader de OpenXR. No
impide cargar el editor; si la sesión de VR no arranca, lo primero es revisar
que SteamVR esté corriendo y sea el runtime activo, antes de tocar el proyecto.

El `PlayerStart_Butaca` queda a 400 cm del centro hacia +X (fuera de la tarima,
lado opuesto al control) y a 70 cm de altura, mirando al centro. Es una
aproximación de la altura de ojo de alguien casi acostado, no un dato medido.

## 8. Cómo abrir

- El proyecto tiene un módulo C++ (`Source/DomoVR/`) y un plugin con código, así
  que la primera vez, o después de tocar código, hay que compilar con el editor
  cerrado: `UnrealBuildTool.exe DomoVREditor Win64 Development -Project="<ruta>\DomoVR.uproject" -WaitMutex`
  (Visual Studio 2022). Salen dos avisos `C4996` de `RHIUpdateTexture2D` en el
  plugin de Spout; son esperables.
- `03_Unreal/abrir_proyecto.ps1` abre el editor (`-culture=en`). La primera
  apertura compila shaders y puede tardar varios minutos con la GPU al 100 %.
- Al abrir arranca solo un servidor MCP en `http://127.0.0.1:8090/mcp` (plugins
  `ModelContextProtocol` y `EditorToolset`, sin autenticación, solo localhost).
  El puerto se fija en `Config/DefaultEditorPerProjectUserSettings.ini` porque el
  8000 de fábrica cae en un rango que Windows reserva en esta máquina.
- Unreal en segundo plano se frena a unos 3 fps. Para que siga a velocidad
  completa mientras se trabaja en TouchDesigner se apagó
  `bThrottleCPUWhenNotForeground` en la configuración del editor del usuario
  (`%LOCALAPPDATA%\UnrealEngine\5.8\Saved\Config\WindowsEditor\EditorSettings.ini`),
  que no viaja con el repositorio.

## 9. Cómo verificar

1. El editor abre directo en `/Game/Maps/DomoVR` con la sala visible (no en un
   nivel `Untitled`).
2. El Outliner tiene `Domo_Actor`, `Muro_Actor`, `Piso_Actor`, `Listones_Actor`,
   `Tarima_Actor`, `Control_Actor`, seis `Butacas_XX_Actor`, cuatro
   `Puerta_XX_Actor`, `PPV_ExposicionFija`, `SkyLight_Domo`, `PlayerStart_Butaca`
   y `SpoutDomeReceiver`.
3. El viewport está en modo **Lit** y en **Realtime** (`Ctrl+R`). En modo Unlit
   los materiales sin iluminación se dibujan como un gris plano y la cúpula
   parece muerta; en un viewport pausado no tickea ningún actor.
4. La cúpula muestra la imagen de TouchDesigner y las butacas cambian de tono
   con ella. Eso confirma que la luz de la sala viene del domo.
5. `Saved/Logs/DomoVR.log` sin errores de `LogSpoutPlugin`. Los bloques
   `LogAutomationTest: Error: Condition failed` con `UnifiedErrorTest` son
   pruebas internas del plugin MCP, no fallos del proyecto.

## 10. Pendiente de confirmar

- **Rango V de la UV de la cúpula: resuelto en la práctica.** Verificado el 17
  de septiembre de 2026 con un patrón de bandas enviado por Spout (capturas en
  `05_Preview/pruebas/unreal_bandas_lateral.png` y `unreal_bandas_cenit.png`):
  la cúpula muestra solo la mitad superior del equirectangular. V = 0,5 cae en
  el horizonte (la línea de arranque de la cúpula sobre los listones), V = 0,75
  en 45° de elevación y V = 1 en el cénit. U = 0,5 cae en +X (el frente del
  público, opuesto a la zona de control en −X), y los meridianos dibujados cada
  45° salieron equiespaciados. Lo que sigue sin explicación es el código:
  `crear_domo()` en `01_Blender/generar_sala_domo.py` escribía
  `v = elevación / 90°` y no se veía dónde se remapeaba a la mitad superior.
  **Resuelto también en el código** (misma noche): `primitive_uv_sphere_add`
  ya traía una capa `UVMap` y el script escribía en una segunda capa
  (`UVMap.001`); Unreal leía el canal 0, la UV por defecto de la esfera
  (`U = azimut/360 + 0,5`, `V = 0,5 + elevación/180`). Ahora la cúpula se
  construye a mano con una sola capa y esa fórmula explícita, igual para los
  tres modelos de sala. Detalle en [05_Modelos_de_sala.md](05_Modelos_de_sala.md),
  sección 3.
- **`EmissiveIntensity`.** Documentado en la sección 5: valor inicial 1,0
  (`importar_sala.py`, línea 185), expuesto en `MI_Domo`. El valor que de verdad
  se ve bien no quedó confirmado a ojo.
- **Ancho del sector de control: cerrado.** Son 7 m: `ANCHO_CONTROL = 7.0` en
  `importar_sala.py` (línea 32) y en el script de Blender.
- **Altura del PlayerStart** (70 cm): aproximación pendiente de ajustar con las
  coordenadas reales de las butacas.
