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
02_Export/texturas/                mapas horneados por Blender (ya no los usa Unreal; ver sección 11)
03_Unreal/generar_texturas_pbr.py  genera las texturas PBR tileables de la sala (numpy -> PNG de 512)
03_Unreal/Texturas_PBR/            esas texturas: tela, madera, alfombra, fieltro, metal cepillado, tarima, pintura, señal de salida
03_Unreal/importar_sala.py         importa el FBX, crea materiales y arma el nivel
03_Unreal/realismo_sala.py         materiales PBR, Nanite, detalles, post proceso y SkyLight; lo usa el importador y corre suelto
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
| `SM_Muro` | `MI_Muro` | fieltro acústico gris oscuro |
| `SM_Piso` | `MI_Piso` | alfombra de bucle gris azulada |
| `SM_Tarima` | `MI_Tarima` | tablas pintadas de negro con rayones |
| `SM_Listones` | `MI_Madera` | nogal barnizado, veta vertical |
| `SM_Control` | `MI_Control` | pintura satinada oscura |
| `SM_Butacas_01` … `SM_Butacas_06` | `MI_Butaca` | tela azul profundo; una malla por cuña, 60 butacas fusionadas |
| `SM_Puerta_01` … `SM_Puerta_04` | `MI_Puerta` | pintura satinada; con marco y hueco real en el muro |

Todas las `MI_*` son instancias de un solo material triplanar, `M_SalaPBR`
(sección 11). En total son unos 43 000 triángulos. Desde el 18 de septiembre
de 2026 todas las mallas llevan Nanite, salvo la cúpula (sección 11).

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
`combine_meshes = False` (una malla por objeto); importa las texturas de
`03_Unreal/Texturas_PBR/` (BaseColor como color sRGB, Roughness en escala de
grises sin sRGB, Normal como `TC_Normalmap` sin sRGB) y crea los materiales,
las dos cosas con `realismo_sala.py`; prende Nanite malla por malla; carga o crea el
nivel y lo vacía de actores; coloca un `StaticMeshActor` por malla; crea el
`PostProcessVolume`, el `SkyLight_Domo` y el `PlayerStart`; coloca los detalles
(señales de salida, luces de pasillo, monitores; sección 11); guarda todo e
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
| Grafo de `M_Domo` | UV con `EspejoU` → `SpoutTexture` (TextureSampleParameter2D) × `EmissiveIntensity` (escalar) → Emissive Color | la textura la sustituye Spout en vivo; la intensidad se ajusta sin recompilar; `EspejoU` = 1 voltea la U para que la imagen de TouchDesigner no salga espejada (sección 13) |
| `EmissiveIntensity` | parámetro escalar de `M_Domo`, valor inicial 1,0 (`importar_sala.py`, línea 185); expuesto en `MI_Domo` | multiplica el frame de Spout antes del pin Emissive Color; se ajusta en vivo desde `MI_Domo` sin recompilar. El valor que se ve bien no está confirmado visualmente |
| Textura de arranque | `/Engine/EngineResources/DefaultTexture` | marcador de posición sRGB; con la grilla lineal el material no compilaba y el domo salía negro |
| `MI_Domo` | instancia de `M_Domo` | es la que lleva la malla y de la que el receptor crea su instancia dinámica |
| `SkyLight_Domo` | en (0, 0, 400), movable, `real_time_capture`, `lower_hemisphere_is_black` (solo en el 180), intensidad 2,5, cubemap de 256 | captura la cúpula cada frame y la reparte como luz sobre butacas, piso y listones |

El punto clave es `is_sky` más el SkyLight con captura en tiempo real. Lumen
por sí solo casi no recoge la emisión de una malla enorme y delgada como la
cúpula: sin esas dos piezas la sala queda negra aunque la cúpula se vea
encendida. Marcada como cielo, el `SkyLight_Domo` la lee cada frame y con ella
tiñe la sala con los colores de lo que se proyecta.

Los demás materiales son instancias de `M_SalaPBR` y `M_SalaEmisivo`; se
describen en la sección 11.

## 6. Post proceso

Un `PostProcessVolume` sin límites (`Unbound`), etiquetado `PPV_ExposicionFija`.
La exposición es manual y fija: con exposición automática la cámara reaccionaría
a la propia imagen proyectada y arruinaría la lectura del contenido.

| Ajuste | Valor |
|---|---|
| Método de exposición | Manual |
| Exposición física de cámara | apagada (con ella la emisión del domo quedaba hundida en negro) |
| Exposure bias | −0,8 (antes −0,5; el papel blanco de *3gracias* se quemaba) |
| Brillo mínimo y máximo | 1,0 / 1,0 |
| Indirect lighting intensity | 1 (antes 8: la sala salía saturada del color del contenido) |
| Lumen: scene lighting quality, scene detail, final gather quality, reflection quality | 2 |
| Reflejos de Lumen: rebotes | 2 |
| Bloom intensity | 0,25 |
| Viñeta | 0,15 (suave) |
| Grano y aberración cromática | 0 |

La oclusión ambiental la da Lumen (su AO de corto alcance, con trazado de
rayos por hardware); el SSAO clásico no se usa con Lumen. Estos valores los
pone `realismo_sala.ajustar_post_proceso`.

En `Config/DefaultEngine.ini` acompañan: Lumen para GI y reflejos
(`r.DynamicGlobalIlluminationMethod=1`, `r.ReflectionMethod=1`) con trazado de
rayos por hardware (`r.RayTracing=True`, `r.Lumen.HardwareRayTracing=True`,
`r.SkinCache.CompileShaders=True`), TSR como anti-aliasing
(`r.AntiAliasingMethod=4`), la captura del SkyLight sin repartir en cuadros
(`r.SkyLight.RealTimeReflectionCapture.TimeSlice=0`, sección 12), campos de
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
  completa mientras se trabaja en TouchDesigner hay que apagar
  `bThrottleCPUWhenNotForeground` en la configuración del editor del usuario
  (`%LOCALAPPDATA%\UnrealEngine\5.8\Saved\Config\WindowsEditor\EditorSettings.ini`),
  que no viaja con el repositorio. El 18 de septiembre de 2026 estaba otra
  vez en `True` y era la mitad del "bug verde" (sección 12); se volvió a poner
  en `False`. Si la sala del editor deja de seguir al contenido, es lo primero
  que hay que mirar.
- La primera apertura después de encender el trazado de rayos recompila
  todos los shaders (globales y de materiales); queda en caché.

## 9. Cómo verificar

1. El editor abre directo en `/Game/Maps/DomoVR` con la sala visible (no en un
   nivel `Untitled`).
2. El Outliner tiene `Domo_Actor`, `Muro_Actor`, `Piso_Actor`, `Listones_Actor`,
   `Tarima_Actor`, `Control_Actor`, seis `Butacas_XX_Actor`, cuatro
   `Puerta_XX_Actor`, `PPV_ExposicionFija`, `SkyLight_Domo`, `PlayerStart_Butaca`,
   `SpoutDomeReceiver`, `DomeMediaController` (en `Fuente = Spout`) y la
   carpeta `Detalles` con 122 actores (señales de salida, luces de pasillo,
   anillo de la tarima, monitores).
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
- **`EmissiveIntensity`: confirmado a ojo.** 1,0 con la exposición de −0,8
  (sección 6) deja el papel de *3gracias* claro sin quemarse y la sala
  iluminada por la cúpula (capturas del 18 de septiembre de 2026).
- **El preset VR en el visor.** No se midió el rendimiento con el trazado de
  rayos por hardware en estéreo; si el visor pierde cuadros, lo primero es
  `r.Lumen.HardwareRayTracing=False` (Lumen vuelve a los campos de
  distancia) antes que tocar Nanite o los materiales.
- **Ancho del sector de control: cerrado.** Son 7 m: `ANCHO_CONTROL = 7.0` en
  `importar_sala.py` (línea 32) y en el script de Blender.
- **Altura del PlayerStart** (70 cm): aproximación pendiente de ajustar con las
  coordenadas reales de las butacas.

## 11. Realismo: materiales, Nanite, trazado de rayos y detalles

Desde el 18 de septiembre de 2026. Todo sale de `03_Unreal/realismo_sala.py`,
que `importar_sala.py` llama en cada importación y que también se corre suelto
sobre los tres niveles ya armados, sin reimportar ni vaciar nada (el receptor
de Spout y el controlador de video quedan como estaban):

```
python 03_Unreal/generar_texturas_pbr.py                    # solo si se cambian las texturas
03_Unreal\importar_sala.ps1 -ScriptName realismo_sala.py     # headless, editor cerrado
```

**Texturas.** `generar_texturas_pbr.py` las fabrica con numpy, sin librería de
materiales: ruido filtrado en el dominio de Fourier (periódico por
construcción, así que cada textura es tileable), 512 × 512, tres mapas por
material (color sRGB, rugosidad lineal, normal) y 3,2 MB en total en
`03_Unreal/Texturas_PBR/`. Es determinista (semilla fija).

| Textura | Qué imita | Escala en la sala | Dónde va |
|---|---|---|---|
| Tela | tapiz de sarga fina, pelusa, motas de uso | 0,30 m por mosaico | butacas |
| Madera | nogal barnizado, veta vertical, poros | 0,60 m | listones del 180 |
| Alfombra | bucle fino con hileras y manchas de desgaste | 0,70 m | pisos, gradas y plataformas |
| Fieltro | panel acústico forrado en tela | 0,80 m | muros |
| MetalCepillado | acero inoxidable cepillado (metálico) | 0,50 m | barandas y pasamanos, marco de la cabina |
| Tarima | tablas pintadas de negro, rayones, zonas pulidas | 1,00 m | tarima central del 180 |
| Pintura | pintura satinada con piel de naranja | 0,60 m | puertas, consola, cajas de las señales |

**`M_SalaPBR`.** Un solo material para todas las superficies, con proyección
triplanar en coordenadas de mundo: la escala se da en metros por mosaico
(`EscalaM`) y es la misma en las tres salas, sin depender de la UV que traiga
cada malla de Blender (la del 180 es de horneado; las de las salas frontales
no tienen una escala útil). Tres nodos Custom leen color, rugosidad y normal;
la normal sale en espacio de mundo (`tangent_space_normal = False`): cada
proyección suma su relieve sobre los ejes de mundo en los que corren su u y su
v. En las caras que miran a X o a Y la v de la textura baja con la altura, así
que la veta de la madera queda vertical. Una variación macro (ruido de valor
3D de 1,9 m, parámetro `Macro`) rompe la repetición a la distancia. El color
final es `textura × Tinte × 2`: las texturas neutras rondan el gris medio y el
color lo pone cada instancia (`Tinte`). Otros parámetros: `RugMul`, `RugAdd`,
`NormalFuerza`, `Metallic` y `Nitidez` (de la mezcla triplanar).

| Instancia | Superficie | Tinte |
|---|---|---|
| `MI_Butaca` (180) | Tela | azul profundo (0,055; 0,07; 0,15) |
| `MI_Butaca` (45) | Tela | rojo de cine (0,16; 0,018; 0,022), algo menos saturado que el color de trabajo de Blender |
| `MI_Piso`, `MI_Grada` | Alfombra | gris azulado oscuro; el piso de la 45 y la 90 toma el color del JSON |
| `MI_Muro` | Fieltro | casi negro |
| `MI_Madera` | Madera | la textura tal cual |
| `MI_Baranda` | MetalCepillado | metálico 1 |
| `MI_Puerta`, `MI_Control` | Pintura | gris oscuro cálido |

Las instancias del 180 viven en `/Game/Sala/Materials`; las de las salas
frontales, en `/Game/Sala/Domo_45/Materials` y `/Game/Sala/Domo_90/Materials`.
Los `M_Muro`, `M_Piso`, … de antes (Materials con los mapas horneados o con
color plano) y las texturas de `/Game/Sala/Textures` se borran.

**`M_SalaEmisivo`.** Color × `Intensidad` × `TexturaEmisiva` en la emisión,
con `BaseColor` y `Roughness` propios. De él salen `MI_LedAmbar` (luces de
pasillo, 2), `MI_LedTarima` (anillo azulado del borde de la tarima, 1,2),
`MI_Salida` (la señal verde, 1,6, con la textura `SenalSalida`), `MI_Monitor`
(0,2) y `MI_VidrioCabina` (vidrio casi negro y pulido con un resplandor cálido
de 0,035). En las salas frontales, `MI_LedPaso` reemplaza al `M_LedPaso` del
JSON, con la misma intensidad que las luces del 180.

**Nanite.** Encendido en todas las mallas estáticas salvo `SM_Domo`
(`realismo_sala.aplicar_nanite`, que el importador llama después de importar;
el FBX se importa sin Nanite). La cúpula se queda sin Nanite porque su
material es de cielo (`is_sky`) y el SkyLight la captura por la ruta clásica.
Cada malla Nanite lleva `fallback_relative_error = 0`, para que el trazado de
rayos use la malla completa (son mallas livianas). `M_SalaPBR`,
`M_SalaEmisivo`, `M_Domo` y `M_DomoMedia` llevan el indicador de uso Nanite:
el aviso `missing usage flag Nanite` de `M_Muro`, `M_Piso`, … ya no aparece
(cero veces en los logs de `-game` de las tres salas).

**Trazado de rayos.** Lumen usa el trazado por hardware (RTX 3090) para GI y
reflejos; el log lo confirma con `Ray tracing is enabled`. Los reflejos se ven
sobre todo en las barandas de metal, que reflejan la cúpula.

**Detalles** (actores con la etiqueta `domo_detalle`, en la carpeta
`Detalles` del Outliner, rehechos en cada corrida):

- Señal de salida sobre cada puerta: caja de pintura oscura de 44 × 19 cm y
  una cara emisiva con figura, flecha y la palabra SALIDA, a 22 cm sobre el
  marco, mirando hacia adentro. La cara es un plano del motor girado con
  `roll 90, pitch 0, yaw = dirección − 90`; con esa rotación el texto se lee
  derecho (`05_Preview/pruebas/unreal_senal_salida.png`).
- En el 180: un LED ámbar en el piso cada 1,2 m a lo largo del eje de cada uno
  de los siete pasillos entre cuñas (los dos que bordean el control llegan
  solo hasta su antepecho), 72 segmentos de luz azulada en el borde superior
  de la tarima y tres monitores tenues en la consola del control. Los ángulos
  de los pasillos se calculan como en el generador de Blender.
- En las salas 45 y 90: la ventana de la cabina de proyección en la pared del
  fondo, 2,3 m por encima de la última fila o plataforma, de 4 × 1,1 m, con
  marco y parteluz de metal.

Lo que no se tocó: la geometría de Blender. Las butacas siguen siendo cajas
sin biselar; biselarlas en el generador sería el siguiente paso para que
atrapen luz en los cantos.

## 12. La luz de la sala sigue al contenido (el "bug verde")

Síntoma: con *3gracias* ya en la cúpula, la sala seguía teñida de verde, el
color del patrón que había antes (las capturas del 17 de septiembre). Dos
causas, las dos corregidas el 18 de septiembre de 2026:

1. `bThrottleCPUWhenNotForeground=True` en el `EditorSettings.ini` del usuario:
   con el editor en segundo plano el mundo tickea a unos 3 cuadros por
   segundo, así que la recaptura del SkyLight y Lumen tardaban decenas de
   segundos en alcanzar al contenido. Se puso en `False` (sección 8).
2. El SkyLight recaptura en unos 12 cuadros repartidos (timesliced) y Lumen
   necesita más cuadros para asentarse.
   `r.SkyLight.RealTimeReflectionCapture.TimeSlice=0` en `DefaultEngine.ini`
   hace la recaptura entera cada cuadro, y antes de cada captura se dejan
   correr unos segundos (cientos de cuadros), no uno solo.

Cómo se comprobó: con TouchDesigner en el patrón (verde) se abrió la sala 180
en `-game`, y a los pocos segundos se pasó TouchDesigner a *3gracias*. La
captura tomada 19 segundos después muestra la sala con el tono del papel, sin
verde: el promedio de la zona de butacas es (33; 34; 42) en 8 bits, verde
sobre rojo 1,02, contra la sala claramente verde con el patrón
(`05_Preview/vista_general_perspectiva.png`).

## 13. El espejo de la U en la ruta de Spout

`06_Unreal_standalone.md` (sección 1) encontró que la U de la cúpula corre al
revés que la de TouchDesigner, y que el patrón simétrico no lo delataba. Se
comprobó en la ruta de Spout con un lienzo asimétrico
(`05_Preview/pruebas/marca_espejo_lienzo.png`: FRENTE en `u 0,5`, IZQUIERDA en
`u 0,37`, DERECHA en `u 0,63`, CENIT arriba) mandado desde el módulo 360 de
TouchDesigner. Antes de corregir, desde el centro de la sala mirando a +X, las
palabras se leían al revés e IZQUIERDA caía a la derecha
(`05_Preview/pruebas/unreal_espejo_antes.png`). La corrección está en
`M_Domo`, no en TouchDesigner ni en la UV de Blender: un parámetro `EspejoU`
(1 por defecto, `ESPEJO_U_INICIAL` en `importar_sala.py`) que usa `1 − U`.
Después, las tres palabras se leen derechas, IZQUIERDA a la izquierda y
FRENTE en +X (`05_Preview/pruebas/unreal_espejo_despues.png`). El frente y la
costura no se mueven, así que nada de lo medido antes con el patrón cambia.
`MI_Domo` lo comparten las tres salas.

## 14. Presets VR y Render, y cómo capturar

Los valores de fábrica del proyecto (`DefaultEngine.ini`) son el preset
**VR**, el liviano. El preset **Render** es para capturas y renders:

| CVar | VR | Render |
|---|---|---|
| `r.ScreenPercentage` | 100 | 200 (TSR reconstruye a la salida) |
| `r.TSR.History.ScreenPercentage` | 100 | 200 |
| `r.Lumen.HardwareRayTracing.LightingMode` | 0 (caché de superficie) | 2 (hit lighting) |
| `r.Lumen.Reflections.DownsampleFactor` | 2 | 1 |
| `r.Lumen.Reflections.MaxRoughnessToTrace` | 0,4 | 0,6 |
| `r.Lumen.ScreenProbeGather.DownsampleFactor` | 16 | 8 |
| `r.Lumen.ScreenProbeGather.TracingOctahedronResolution` | 8 | 12 |

Se cambia con `domo.Preset VR|Render` en la consola, con `-DomoPreset=Render`
en la línea de comandos o desde Blueprint (`AplicarPreset`, en
`ADomeMediaController`). En el visor conviene quedarse en VR: el preset Render
a 200 % no es para tiempo real en estéreo.

Las capturas de `05_Preview/renders/` y las vistas `05_Preview/vista_*`
(salvo las plantas cenitales, que siguen siendo de Blender) se hicieron así,
sin ventana ni foco, con TouchDesigner mandando por Spout:

```
UnrealEditor.exe <ruta>\DomoVR.uproject /Game/Maps/DomoVR -game -RenderOffscreen -nohmd ^
  -ResX=1920 -ResY=1080 -windowed -DomoFuente=Spout -DomoGuion=<guion> -abslog=<log>
```

con un guion como:

```
esperar 15
domo.Preset Render
domo.Camara -800 0 700 -30 0 100
esperar 6
HighResShot 1920x1080 filename=C:/tmp/general.png
quit
```

`-DomoFuente=Spout` hace falta porque fuera del editor el controlador arranca
en Media (`06_Unreal_standalone.md`, sección 5). Las `esperar` después de
mover la cámara son el calentamiento de Lumen y del SkyLight. Las rutas del
guion y del log tienen que ser absolutas. Si el mapa se pasa desde Git Bash,
hace falta `MSYS_NO_PATHCONV=1`: si no, `/Game/Maps/DomoVR_45` llega convertido
en una ruta de Windows y el juego abre el mapa por defecto. Y TouchDesigner
tiene que estar a la vista (no minimizado), o no cocina y la cúpula se queda
con el último cuadro que recibió.

| Captura | Cámara (`domo.Camara X Y Z Pitch Yaw FOV`) |
|---|---|
| `3gracias_unreal_general.png` | −800 0 700 −30 0 100 |
| `3gracias_unreal_desde_butacas.png` | −430 190 125 30 −8 95 |
| `3gracias_unreal_desde_butacas_02.png` (reclinado, hacia el cénit) | 150 −700 110 60 150 100 |
| `3gracias_unreal_general_02.png` (hacia el control) | 820 0 720 −32 180 100 |
| `3gracias_sala45_butaca.png` | −363 −92 372 18 3,7 100 (el ojo de la fila 7) |
| `3gracias_sala45_general.png` | −780 520 720 −18 −22 100 |
| `3gracias_sala90_de_pie.png` | −93 −145 270 5,7 7,5 100 (el ojo de la plataforma 3) |
| `3gracias_sala90_general.png` | −560 450 620 −15 −25 100 |
